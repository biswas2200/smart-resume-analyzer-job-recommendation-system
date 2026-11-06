package com.resumeanalyser.common.aspect;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * Logs entry, completion time, and failures for every controller and service
 * method in the app, using Spring AOP -- so logging stays out of the business
 * logic itself. The two {@link Pointcut}s below match any class whose simple
 * name ends in "Controller" or "Service" under {@code com.resumeanalyser},
 * so a brand new module gets this logging automatically the moment it adds a
 * class following that naming convention -- no per-module wiring needed.
 */
@Aspect
@Component
@Order(1)
public class LoggingAspect {

    /** Matches every public method on any class named {@code *Controller}. */
    @Pointcut("execution(public * com.resumeanalyser..*Controller.*(..))")
    public void controllerMethods() {}

    /** Matches every public method on any class named {@code *Service}. */
    @Pointcut("execution(public * com.resumeanalyser..*Service.*(..))")
    public void serviceMethods() {}

    /**
     * Wraps a matched method call: logs that it started, how long it took, and
     * whether it succeeded or threw.
     * <p>
     * Method arguments and return values are intentionally never logged: request
     * DTOs in this app carry raw passwords ({@code RegisterRequest}/{@code LoginRequest})
     * and responses carry JWTs ({@code AuthResponse}) that must never end up in
     * application logs.
     *
     * @param joinPoint the intercepted method call, supplied by Spring AOP
     * @return whatever the wrapped method returns, unchanged
     * @throws Throwable whatever the wrapped method throws, rethrown unchanged after logging
     */
    @Around("controllerMethods() || serviceMethods()")
    public Object logExecution(ProceedingJoinPoint joinPoint) throws Throwable {
        Logger log = LoggerFactory.getLogger(joinPoint.getTarget().getClass());
        String method = joinPoint.getSignature().toShortString();
        long start = System.currentTimeMillis();

        log.debug("-> {}", method);
        try {
            Object result = joinPoint.proceed();
            log.info("{} completed in {}ms", method, System.currentTimeMillis() - start);
            return result;
        } catch (Throwable ex) {
            log.warn("{} failed in {}ms: {}: {}",
                    method, System.currentTimeMillis() - start, ex.getClass().getSimpleName(), ex.getMessage());
            throw ex;
        }
    }
}
