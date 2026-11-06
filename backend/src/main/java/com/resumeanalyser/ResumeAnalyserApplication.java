package com.resumeanalyser;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the Smart Resume Analyser and Job Recommendation System backend.
 * Boots the Spring application context, which wires up every module
 * (account, auth, resume, recommendation, feedback, skillvector, common)
 * found under the com.resumeanalyser package.
 */
@SpringBootApplication
public class ResumeAnalyserApplication {

    /**
     * Starts the embedded web server and the Spring application context.
     *
     * @param args standard Java command-line arguments, passed straight through to Spring Boot
     */
    public static void main(String[] args) {
        SpringApplication.run(ResumeAnalyserApplication.class, args);
    }
}
