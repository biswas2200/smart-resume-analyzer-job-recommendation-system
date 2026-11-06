package com.resumeanalyser.resume;

import com.resumeanalyser.account.User;
import com.resumeanalyser.account.UserRole;
import com.resumeanalyser.client.MlServiceClient;
import com.resumeanalyser.client.MlServiceException;
import com.resumeanalyser.client.dto.AnalyzeResponseDto;
import com.resumeanalyser.client.dto.AtsScoreResponseDto;
import com.resumeanalyser.client.dto.DomainDetectionDto;
import com.resumeanalyser.client.dto.ResumeProfileDto;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.recommendation.RecommendationService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;

import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * Unit tests for {@link ResumeService}: every account is analysed the same way
 * (the AI engine for any field, five roles), what of the detected domain and
 * lock state is persisted, how re-analysis replaces an earlier run, and that
 * resume versions and JD match are open to every account.
 */
@ExtendWith(MockitoExtension.class)
class ResumeServiceTest {

    @Mock
    private ResumeRepository resumeRepository;

    @Mock
    private ParsedProfileRepository parsedProfileRepository;

    @Mock
    private ResumeStorageService storageService;

    @Mock
    private MlServiceClient mlServiceClient;

    @Mock
    private RecommendationService recommendationService;

    private ResumeService resumeService;

    @BeforeEach
    void setUp() {
        resumeService = new ResumeService(
                resumeRepository, parsedProfileRepository, storageService, mlServiceClient, recommendationService);
    }

    @Test
    void upload_analysesWithFiveRoles_forEveryRole() {
        for (UserRole role : UserRole.values()) {
            User user = userWithRole(role);
            stubSuccessfulUpload(user);

            resumeService.upload(user, fakeFile());
        }

        verify(mlServiceClient, times(UserRole.values().length)).analyzeFile(any(), anyString(), eq(5));
    }

    @Test
    void upload_leavesNothingBehind_whenTheAnalysisFails() {
        User user = userWithRole(UserRole.USER);
        when(resumeRepository.countByUser(user)).thenReturn(0);
        when(mlServiceClient.analyzeFile(any(), anyString(), anyInt()))
                .thenThrow(new MlServiceException("The AI engine is unavailable", false, true, null));

        assertThatThrownBy(() -> resumeService.upload(user, fakeFile())).isInstanceOf(MlServiceException.class);

        verifyNoInteractions(storageService);
        verify(resumeRepository, never()).save(any());
        verify(parsedProfileRepository, never()).save(any());
    }

    @Test
    void upload_persistsTheDetectedDomainAndLockState() {
        User user = userWithRole(UserRole.USER);
        stubSuccessfulUpload(user);
        when(mlServiceClient.analyzeFile(any(), anyString(), anyInt())).thenReturn(lockedAnalysis());

        resumeService.upload(user, fakeFile());

        ArgumentCaptor<ParsedProfile> saved = ArgumentCaptor.forClass(ParsedProfile.class);
        verify(parsedProfileRepository).save(saved.capture());
        ParsedProfile profile = saved.getValue();
        assertThat(profile.getDomain()).isEqualTo("healthcare");
        assertThat(profile.getDomainName()).isEqualTo("Healthcare & Life Sciences");
        assertThat(profile.getDomainConfidence()).isEqualTo(0.86);
        assertThat(profile.getDomainEngine()).isEqualTo("llm");
        assertThat(profile.isRecommendationsLocked()).isTrue();
        assertThat(profile.getLockReason()).isEqualTo("community_edition");
    }

    @Test
    void reanalyze_reReadsTheStoredFile_andReplacesProfileAndRecommendations() {
        User user = userWithRole(UserRole.USER);
        Resume resume = new Resume();
        resume.setId(UUID.randomUUID());
        resume.setUser(user);
        resume.setFileRef(user.getId() + "/2-nurse.docx");
        ParsedProfile existing = new ParsedProfile();
        existing.setResume(resume);
        existing.setRecommendationsLocked(true);
        existing.setLockReason("community_edition");
        when(resumeRepository.findById(resume.getId())).thenReturn(Optional.of(resume));
        when(storageService.read(resume.getFileRef())).thenReturn("stored bytes".getBytes());
        when(parsedProfileRepository.findByResume(resume)).thenReturn(Optional.of(existing));
        when(mlServiceClient.analyzeFile(any(), anyString(), anyInt())).thenReturn(fakeAnalysis());

        resumeService.reanalyze(user, resume.getId());

        verify(mlServiceClient).analyzeFile(eq("stored bytes".getBytes()), eq("nurse.docx"), eq(5));
        verify(parsedProfileRepository).save(existing);  // updated in place, not a second row
        assertThat(existing.isRecommendationsLocked()).isFalse();
        assertThat(existing.getLockReason()).isNull();
        verify(recommendationService).replaceForResume(eq(user), eq(resume), any());
    }

    @Test
    void reanalyze_rejectsAResumeThatBelongsToSomeoneElse() {
        User owner = userWithRole(UserRole.USER);
        User other = userWithRole(UserRole.USER);
        Resume resume = new Resume();
        resume.setId(UUID.randomUUID());
        resume.setUser(owner);
        when(resumeRepository.findById(resume.getId())).thenReturn(Optional.of(resume));

        assertThatThrownBy(() -> resumeService.reanalyze(other, resume.getId()))
                .isInstanceOf(ResourceNotFoundException.class);
        verifyNoInteractions(mlServiceClient);
    }

    @Test
    void matchJobDescription_usesTheStoredSkillsAndDomain_andNeverReparses_forAnyAccount() {
        User user = userWithRole(UserRole.USER);
        Resume resume = new Resume();
        resume.setId(UUID.randomUUID());
        resume.setUser(user);
        ParsedProfile profile = new ParsedProfile();
        profile.setResume(resume);
        profile.setSkills(List.of("Nursing", "ACLS"));
        profile.setDomain("healthcare");
        when(resumeRepository.findById(resume.getId())).thenReturn(Optional.of(resume));
        when(parsedProfileRepository.findByResume(resume)).thenReturn(Optional.of(profile));
        when(mlServiceClient.matchJd(List.of("Nursing", "ACLS"), "RN needed: ACLS, BLS", "healthcare"))
                .thenReturn(new com.resumeanalyser.client.dto.JdMatchResponseDto(
                        0.55, 0.5, 0.6, List.of("ACLS", "BLS"), List.of("ACLS"), List.of("BLS"),
                        new com.resumeanalyser.client.dto.RoleMatchDto(
                                "Registered Nurse", "healthcare", "desc", 0.8, List.of(), List.of()),
                        "covers 1 of 2"));

        var result = resumeService.matchJobDescription(user, resume.getId(), "RN needed: ACLS, BLS");

        assertThat(result.resumeId()).isEqualTo(resume.getId());
        assertThat(result.score()).isEqualTo(0.55);
        assertThat(result.missingSkills()).containsExactly("BLS");
        assertThat(result.closestRole().title()).isEqualTo("Registered Nurse");
        verify(mlServiceClient, never()).analyzeFile(any(), anyString(), anyInt());
        verifyNoInteractions(storageService);
    }

    @Test
    void matchJobDescription_rejectsAResumeThatBelongsToSomeoneElse() {
        User owner = userWithRole(UserRole.USER);
        User other = userWithRole(UserRole.USER);
        Resume resume = new Resume();
        resume.setId(UUID.randomUUID());
        resume.setUser(owner);
        when(resumeRepository.findById(resume.getId())).thenReturn(Optional.of(resume));

        assertThatThrownBy(() -> resumeService.matchJobDescription(other, resume.getId(), "any"))
                .isInstanceOf(ResourceNotFoundException.class);
        verifyNoInteractions(mlServiceClient);
    }

    @Test
    void filenameOf_recoversTheOriginalNameFromTheObjectKey() {
        assertThat(ResumeService.filenameOf("user-id/3-my-resume.pdf")).isEqualTo("my-resume.pdf");
        assertThat(ResumeService.filenameOf("user-id/1-resume")).isEqualTo("resume");
    }

    @Test
    void listVersions_returnsEveryVersion() {
        User user = userWithRole(UserRole.USER);
        when(resumeRepository.findByUserOrderByVersionAsc(user)).thenReturn(resumesWithVersions(1, 2, 3, 4, 5));

        List<Resume> result = resumeService.listVersions(user);

        assertThat(result).extracting(Resume::getVersion).containsExactly(1, 2, 3, 4, 5);
    }

    private void stubSuccessfulUpload(User user) {
        when(resumeRepository.countByUser(user)).thenReturn(0);
        when(storageService.store(any(), anyInt(), anyString(), any())).thenReturn("object-key");
        when(resumeRepository.save(any(Resume.class))).thenAnswer(inv -> inv.getArgument(0));
        when(mlServiceClient.analyzeFile(any(), anyString(), anyInt()))
                .thenReturn(fakeAnalysis());
    }

    private AnalyzeResponseDto fakeAnalysis() {
        return new AnalyzeResponseDto(
                new ResumeProfileDto("Jane Doe", "jane@example.com", "", List.of(), List.of(), List.of()),
                new DomainDetectionDto("engineering", "Engineering & Technology", 0.79, "local"),
                new AtsScoreResponseDto(50, 70, List.of()),
                List.of(),
                List.of(),
                false,
                null,
                "explanation text",
                "template",
                false);
    }

    /** A non-engineering analysis that ran on the AI engine (unlocked). */
    private AnalyzeResponseDto aiAnalysis(boolean aiExtractionUsed) {
        return new AnalyzeResponseDto(
                new ResumeProfileDto("Maria Lopez", "", "", List.of("Nursing"), List.of(), List.of()),
                new DomainDetectionDto("healthcare", "Healthcare & Life Sciences", 0.86, "llm"),
                new AtsScoreResponseDto(45, 80, List.of()),
                List.of(),
                List.of(),
                false,
                null,
                "explanation text",
                "template",
                aiExtractionUsed);
    }

    private AnalyzeResponseDto lockedAnalysis() {
        return new AnalyzeResponseDto(
                new ResumeProfileDto("Maria Lopez", "", "", List.of("Nursing"), List.of(), List.of()),
                new DomainDetectionDto("healthcare", "Healthcare & Life Sciences", 0.86, "llm"),
                new AtsScoreResponseDto(45, 80, List.of()),
                List.of(),
                List.of(),
                true,
                "community_edition",
                "locked explanation",
                "template",
                false);
    }

    private User userWithRole(UserRole role) {
        User user = new User();
        user.setId(UUID.randomUUID());
        user.setRole(role);
        return user;
    }

    private MockMultipartFile fakeFile() {
        return new MockMultipartFile("file", "resume.pdf", "application/pdf", "fake pdf bytes".getBytes());
    }

    private List<Resume> resumesWithVersions(int... versions) {
        return Arrays.stream(versions)
                .mapToObj(v -> {
                    Resume resume = new Resume();
                    resume.setId(UUID.randomUUID());
                    resume.setVersion(v);
                    return resume;
                })
                .toList();
    }
}
