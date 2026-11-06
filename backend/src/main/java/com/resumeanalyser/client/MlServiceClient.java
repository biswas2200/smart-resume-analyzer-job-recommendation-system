package com.resumeanalyser.client;

import com.resumeanalyser.client.dto.AnalyzeResponseDto;
import com.resumeanalyser.client.dto.JdMatchRequestDto;
import com.resumeanalyser.client.dto.JdMatchResponseDto;
import com.resumeanalyser.client.dto.JobSkillsDto;
import com.resumeanalyser.client.dto.MarketDemandDto;
import com.resumeanalyser.client.dto.RankJobsDto;
import com.resumeanalyser.skillvector.dto.WeightsSnapshotDto;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * Typed HTTP client wrapping calls to the ML service: {@code /analyze-file}
 * (see {@code ml-service/app/routers/upload.py}) -- a single round trip
 * covering parsing, ATS scoring, role matching, gap analysis, and explanation
 * for an uploaded resume file -- and {@code /match-jd}
 * ({@code routers/analyze.py}), the JD-targeted match over an
 * already-extracted skill set; and the job recommendation pair
 * {@code /extract-job-skills} and {@code /rank-jobs} ({@code routers/jobs.py}).
 */
@Component
public class MlServiceClient {

    private final RestClient restClient;

    public MlServiceClient(RestClient mlServiceRestClient) {
        this.restClient = mlServiceRestClient;
    }

    /**
     * Runs the full resume analysis pipeline on an uploaded file's raw bytes.
     *
     * @param fileBytes the resume file's raw bytes, as received from the client
     * @param filename  the original filename, used by the ML service to pick a
     *                  text extractor by extension (PDF today; see
     *                  {@code document_extraction/registry.py})
     * @param topN      how many top-matched roles to return
     * @return the parsed profile, detected domain, ATS score, role matches, skill gaps, and explanation
     * @throws MlServiceException if the ML service is unreachable, or rejects the
     *                            request (e.g. an unsupported file format --
     *                            see {@link MlServiceException#isUnsupportedFileType()};
     *                            or its LLM provider is unavailable --
     *                            see {@link MlServiceException#isLlmUnavailable()})
     */
    public AnalyzeResponseDto analyzeFile(
            byte[] fileBytes, String filename, int topN) {
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("file", new ByteArrayResource(fileBytes) {
            @Override
            public String getFilename() {
                return filename;
            }
        });

        try {
            return restClient.post()
                    .uri(uriBuilder -> uriBuilder.path("/analyze-file")
                            .queryParam("top_n", topN)
                            .build())
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(builder.build())
                    .retrieve()
                    .body(AnalyzeResponseDto.class);
        } catch (HttpClientErrorException e) {
            boolean unsupportedFileType = e.getStatusCode() == HttpStatus.UNSUPPORTED_MEDIA_TYPE;
            throw new MlServiceException(
                    unsupportedFileType
                            ? "This resume file format isn't supported yet"
                            : "The ML service rejected the request (" + e.getStatusCode() + ")",
                    unsupportedFileType,
                    e);
        } catch (HttpServerErrorException e) {
            if (e.getStatusCode() == HttpStatus.SERVICE_UNAVAILABLE) {
                throw new MlServiceException(
                        "The AI engine for this analysis is temporarily unavailable -- please try again later",
                        false, true, e);
            }
            throw new MlServiceException("The ML service failed (" + e.getStatusCode() + ")", false, e);
        } catch (ResourceAccessException e) {
            throw new MlServiceException("Could not reach the ML service", false, e);
        } catch (RestClientException e) {
            throw new MlServiceException("The ML service call failed", false, e);
        }
    }

    /**
     * Scores an already-extracted skill set against one pasted job description
     * (FR-8.2) -- deterministic on the ML side, no LLM involved.
     *
     * @param skills the candidate's skills as stored on their {@code ParsedProfile}
     * @param jdText the job description, free text
     * @param domain the resume's detected domain, for the closest-role hint
     * @throws MlServiceException if the ML service is unreachable or rejects the request
     */
    public JdMatchResponseDto matchJd(java.util.List<String> skills, String jdText, String domain) {
        try {
            return restClient.post()
                    .uri("/match-jd")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new JdMatchRequestDto(skills, jdText, domain))
                    .retrieve()
                    .body(JdMatchResponseDto.class);
        } catch (HttpClientErrorException e) {
            throw new MlServiceException("The ML service rejected the job description (" + e.getStatusCode() + ")", false, e);
        } catch (HttpServerErrorException e) {
            throw new MlServiceException("The ML service failed (" + e.getStatusCode() + ")", false, e);
        } catch (ResourceAccessException e) {
            throw new MlServiceException("Could not reach the ML service", false, e);
        } catch (RestClientException e) {
            throw new MlServiceException("The ML service call failed", false, e);
        }
    }

    /**
     * The skills each job posting asks for, extracted once when it is stored.
     *
     * @throws MlServiceException if the ML service is unreachable or rejects the request
     */
    public JobSkillsDto.Response extractJobSkills(java.util.List<JobSkillsDto.JobText> jobs) {
        return postJson("/extract-job-skills", new JobSkillsDto.Request(jobs), JobSkillsDto.Response.class);
    }

    /**
     * Ranks jobs for a resume, best first, each with its matched and missing
     * skills and a one-line reason -- deterministic on the ML side, no LLM.
     *
     * @throws MlServiceException if the ML service is unreachable or rejects the request
     */
    public RankJobsDto.Response rankJobs(RankJobsDto.Request request) {
        return postJson("/rank-jobs", request, RankJobsDto.Response.class);
    }

    /**
     * Per catalogue role, the skills open jobs ask for and the EMA signal for
     * each of the role's catalogue skills.
     *
     * @throws MlServiceException if the ML service is unreachable or rejects the request
     */
    public MarketDemandDto.Response marketDemand(java.util.List<RankJobsDto.Job> jobs) {
        return postJson("/market-demand", new MarketDemandDto.Request(jobs), MarketDemandDto.Response.class);
    }

    /**
     * Installs the current EMA weights in the ML service (FR-7.5), so role
     * matching uses them from its next request.
     *
     * @throws MlServiceException if the ML service is unreachable or rejects the snapshot
     */
    public void pushWeights(WeightsSnapshotDto snapshot) {
        try {
            restClient.put()
                    .uri("/weights-snapshot")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(snapshot)
                    .retrieve()
                    .toBodilessEntity();
        } catch (RestClientException e) {
            throw new MlServiceException("Could not install the weights snapshot in the ML service", false, e);
        }
    }

    private <T> T postJson(String path, Object body, Class<T> type) {
        try {
            return restClient.post()
                    .uri(path)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(type);
        } catch (HttpClientErrorException e) {
            throw new MlServiceException("The ML service rejected the request (" + e.getStatusCode() + ")", false, e);
        } catch (HttpServerErrorException e) {
            throw new MlServiceException("The ML service failed (" + e.getStatusCode() + ")", false, e);
        } catch (ResourceAccessException e) {
            throw new MlServiceException("Could not reach the ML service", false, e);
        } catch (RestClientException e) {
            throw new MlServiceException("The ML service call failed", false, e);
        }
    }
}
