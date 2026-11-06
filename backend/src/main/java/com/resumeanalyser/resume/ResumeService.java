package com.resumeanalyser.resume;

import com.resumeanalyser.account.User;
import com.resumeanalyser.client.MlServiceClient;
import com.resumeanalyser.client.dto.AnalyzeResponseDto;
import com.resumeanalyser.client.dto.JdMatchResponseDto;
import com.resumeanalyser.client.dto.ResumeProfileDto;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.recommendation.RecommendationService;
import com.resumeanalyser.resume.dto.JdMatchResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.UUID;

/**
 * Orchestrates a resume upload end to end: validates the file (FR-1.1/1.3),
 * stores it, runs it through the ML service's full analysis pipeline in one
 * call, and persists the results -- the {@link Resume} and its
 * {@link ParsedProfile} here, and the resulting role {@link com.resumeanalyser.recommendation.Recommendation}
 * rows via {@link RecommendationService} (which owns that entity).
 * <p>
 * A single ML call ({@code POST /analyze-file}) covers parsing, ATS scoring,
 * role matching, and explanation -- calling it once here (rather than once per
 * module) avoids re-uploading/re-extracting the same file twice.
 */
@Service
public class ResumeService {

    private static final long MAX_FILE_SIZE_BYTES = 5L * 1024 * 1024;
    private static final Logger log = LoggerFactory.getLogger(ResumeService.class);

    /** How many role matches an analysis returns. */
    private static final int TOP_N = 5;

    private final ResumeRepository resumeRepository;
    private final ParsedProfileRepository parsedProfileRepository;
    private final ResumeStorageService storageService;
    private final MlServiceClient mlServiceClient;
    private final RecommendationService recommendationService;

    public ResumeService(
            ResumeRepository resumeRepository,
            ParsedProfileRepository parsedProfileRepository,
            ResumeStorageService storageService,
            MlServiceClient mlServiceClient,
            RecommendationService recommendationService
    ) {
        this.resumeRepository = resumeRepository;
        this.parsedProfileRepository = parsedProfileRepository;
        this.storageService = storageService;
        this.mlServiceClient = mlServiceClient;
        this.recommendationService = recommendationService;
    }

    /**
     * Validates, stores, and analyzes a newly uploaded resume file, persisting
     * it as the user's next version (FR-1.5).
     *
     * @param user the uploading account
     * @param file the uploaded resume file
     * @return the newly created resume version
     * @throws InvalidResumeFileException if the file is empty or over 5 MB
     * @throws com.resumeanalyser.client.MlServiceException if the ML service rejects
     *         the file's format or is unreachable
     */
    @Transactional
    public Resume upload(User user, MultipartFile file) {
        validate(file);

        int nextVersion = resumeRepository.countByUser(user) + 1;
        byte[] bytes = readBytes(file);
        // Analysed before anything is stored or saved: a failed analysis (the AI engine is
        // unavailable, an unsupported format) must not leave an empty version in the history.
        AnalyzeResponseDto analysis = analyze(user, bytes, file.getOriginalFilename());
        String fileRef = storageService.store(user.getId(), nextVersion, file.getOriginalFilename(), bytes);

        Resume resume = new Resume();
        resume.setUser(user);
        resume.setFileRef(fileRef);
        resume.setVersion(nextVersion);
        resumeRepository.save(resume);

        parsedProfileRepository.save(applyAnalysis(new ParsedProfile(), resume, analysis));
        recommendationService.persistFromAnalysis(user, resume, analysis.matches());

        return resume;
    }

    /** One ML-service analysis: the AI engine for any field, five roles and the AI-written coaching text. */
    private AnalyzeResponseDto analyze(User user, byte[] bytes, String filename) {
        AnalyzeResponseDto analysis = mlServiceClient.analyzeFile(bytes, filename, TOP_N);
        // Outcome only: ids, domain and scores, never resume content.
        log.info("Analysis for user {}: domain={} engine={} ats={} matches={} locked={}{} aiExtraction={} explanation={}",
                user.getId(),
                analysis.domain() == null ? null : analysis.domain().domain(),
                analysis.domain() == null ? null : analysis.domain().engine(),
                analysis.atsScore() == null ? null : analysis.atsScore().score(),
                analysis.matches() == null ? 0 : analysis.matches().size(),
                analysis.recommendationsLocked(),
                analysis.lockReason() == null ? "" : " (" + analysis.lockReason() + ")",
                analysis.aiExtractionUsed(), analysis.explanationSource());
        return analysis;
    }

    /**
     * Re-runs the analysis of an existing resume version, replacing its
     * {@link ParsedProfile} and recommendations in place. This is how a result
     * that was locked at upload time ({@link ParsedProfile#isRecommendationsLocked()},
     * e.g. the AI engine was unavailable) is recovered; the stored file is re-read from object storage, so nothing has to be
     * uploaded again.
     *
     * @throws ResourceNotFoundException if the resume doesn't exist or doesn't belong to this user
     * @throws com.resumeanalyser.client.MlServiceException if the ML service call fails
     */
    @Transactional
    public Resume reanalyze(User user, UUID resumeId) {
        Resume resume = ownedResume(user, resumeId);
        byte[] bytes = storageService.read(resume.getFileRef());
        AnalyzeResponseDto analysis = analyze(user, bytes, filenameOf(resume.getFileRef()));

        ParsedProfile profile = parsedProfileRepository.findByResume(resume).orElseGet(ParsedProfile::new);
        parsedProfileRepository.save(applyAnalysis(profile, resume, analysis));
        recommendationService.replaceForResume(user, resume, analysis.matches());

        return resume;
    }

    /** Every version a user has uploaded, oldest first (FR-1.5). */
    public List<Resume> listVersions(User user) {
        List<Resume> versions = resumeRepository.findByUserOrderByVersionAsc(user);
        return versions;
    }

    /**
     * Recovers the original filename from a {@link ResumeStorageService#store}
     * object key ({@code "<userId>/<version>-<filename>"}) -- the ML service
     * picks its text extractor from the extension.
     */
    static String filenameOf(String fileRef) {
        String key = fileRef.substring(fileRef.indexOf('/') + 1);
        int dash = key.indexOf('-');
        return dash >= 0 ? key.substring(dash + 1) : key;
    }

    private Resume ownedResume(User user, UUID resumeId) {
        return resumeRepository.findById(resumeId)
                .filter(r -> r.getUser().getId().equals(user.getId()))
                .orElseThrow(() -> new ResourceNotFoundException("Resume not found: " + resumeId));
    }

    /**
     * The structured profile extracted from one of the user's resume versions.
     *
     * @throws ResourceNotFoundException if the resume doesn't exist, doesn't belong to
     *         this user, or hasn't been analyzed yet
     */
    public ParsedProfile getParsedProfile(User user, UUID resumeId) {
        Resume resume = ownedResume(user, resumeId);

        return parsedProfileRepository.findByResume(resume)
                .orElseThrow(() -> new ResourceNotFoundException("No parsed profile for resume: " + resumeId));
    }

    /**
     * Matches one of the user's resume versions against a pasted job
     * description (FR-8.1/8.2) using the skills and domain already extracted
     * for it -- no re-parsing, no LLM; nothing is persisted.
     *
     * @throws ResourceNotFoundException if the resume doesn't exist, doesn't belong to
     *         this user, or hasn't been analysed yet
     * @throws com.resumeanalyser.client.MlServiceException if the ML service call fails
     */
    public JdMatchResponse matchJobDescription(User user, UUID resumeId, String jdText) {
        ParsedProfile profile = getParsedProfile(user, resumeId);
        JdMatchResponseDto match = mlServiceClient.matchJd(profile.getSkills(), jdText, profile.getDomain());
        JdMatchResponse.ClosestRole closest = match.closestRole() == null ? null
                : new JdMatchResponse.ClosestRole(
                        match.closestRole().role(), match.closestRole().description(),
                        match.closestRole().domain(), match.closestRole().score());
        return new JdMatchResponse(
                resumeId, match.score(), match.coverage(), match.similarity(),
                match.jdSkills(), match.matchedSkills(), match.missingSkills(), closest, match.explanation());
    }

    private void validate(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new InvalidResumeFileException("The uploaded file is empty");
        }
        if (file.getSize() > MAX_FILE_SIZE_BYTES) {
            throw new InvalidResumeFileException("File is too large — the maximum size is 5 MB");
        }
    }

    private byte[] readBytes(MultipartFile file) {
        try {
            return file.getBytes();
        } catch (IOException e) {
            throw new UncheckedIOException("Failed to read uploaded file", e);
        }
    }

    /** Copies one ML analysis onto a (new or existing) profile row for {@code resume}. */
    private ParsedProfile applyAnalysis(ParsedProfile entity, Resume resume, AnalyzeResponseDto analysis) {
        ResumeProfileDto profile = analysis.profile();

        entity.setResume(resume);
        entity.setName(profile.name());
        entity.setEmail(profile.email());
        entity.setPhone(profile.phone());
        entity.setSkills(profile.skills());
        entity.setExperience(profile.experience().stream()
                .map(e -> new ParsedProfile.ExperienceEntry(e.title(), e.organization(), e.duration(), e.description()))
                .toList());
        entity.setEducation(profile.education().stream()
                .map(e -> new ParsedProfile.EducationEntry(e.degree(), e.institution(), e.year()))
                .toList());
        entity.setAtsScore(analysis.atsScore().score());
        entity.setAtsMaxScore(analysis.atsScore().maxScore());
        entity.setAtsChecks(analysis.atsScore().checks().stream()
                .map(c -> new ParsedProfile.AtsCheckEntry(c.name(), c.passed(), c.detail()))
                .toList());
        entity.setExplanation(analysis.explanation());
        entity.setExplanationSource(analysis.explanationSource());
        if (analysis.domain() != null) {
            entity.setDomain(analysis.domain().domain());
            entity.setDomainName(analysis.domain().name());
            entity.setDomainConfidence(analysis.domain().confidence());
            entity.setDomainEngine(analysis.domain().engine());
        }
        entity.setRecommendationsLocked(analysis.recommendationsLocked());
        entity.setLockReason(analysis.recommendationsLocked() ? analysis.lockReason() : null);
        return entity;
    }
}
