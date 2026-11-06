package com.resumeanalyser.common;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Swagger UI ({@code /swagger-ui/index.html}) and the raw OpenAPI document
 * ({@code /v3/api-docs}) are generated automatically by springdoc from the
 * controllers/DTOs already in the app -- this class only adds the one thing
 * springdoc can't infer: a "Bearer" security scheme, so a JWT pasted into
 * Swagger UI's Authorize button is sent as {@code Authorization: Bearer <token>}
 * on every subsequent call, the same way a real client would.
 */
@Configuration
public class OpenApiConfig {

    private static final String BEARER_SCHEME_NAME = "bearerAuth";

    @Bean
    public OpenAPI resumeAnalyserOpenApi() {
        return new OpenAPI()
                .info(new Info()
                        .title("Smart Resume Analyser and Job Recommendation System API")
                        .description("Auth, resume upload/versioning, recommendations, feedback, and the skill-vector store.")
                        .version("v1"))
                .components(new Components()
                        .addSecuritySchemes(BEARER_SCHEME_NAME, new SecurityScheme()
                                .type(SecurityScheme.Type.HTTP)
                                .scheme("bearer")
                                .bearerFormat("JWT")))
                .addSecurityItem(new SecurityRequirement().addList(BEARER_SCHEME_NAME));
    }
}
