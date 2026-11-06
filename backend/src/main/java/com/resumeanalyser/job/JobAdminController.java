package com.resumeanalyser.job;

import com.resumeanalyser.job.dto.AddCompanyRequest;
import com.resumeanalyser.job.dto.CompanyDto;
import com.resumeanalyser.job.dto.JobsStatusDto;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

/**
 * Admin controls for job collection. The long tasks run in the background
 * ({@link JobsRunner}): they answer 202 at once, or 409 if one is already
 * running; {@code GET /admin/jobs/status} shows progress.
 */
@RestController
@RequestMapping("/admin/jobs")
@PreAuthorize("hasRole('ADMIN')")
public class JobAdminController {

    private final JobsRunner runner;
    private final CompanyService companyService;
    private final CompanyRepository companies;
    private final JobPostingRepository postings;

    public JobAdminController(JobsRunner runner, CompanyService companyService,
                              CompanyRepository companies, JobPostingRepository postings) {
        this.runner = runner;
        this.companyService = companyService;
        this.companies = companies;
        this.postings = postings;
    }

    /** Seeds Bengaluru companies from Wikidata and looks for each one's job feed. */
    @PostMapping("/discover")
    public ResponseEntity<JobsStatusDto> discover() {
        return started(runner.startDiscover());
    }

    /** Adds the Bangalore Startup Map's companies (public pages only) and reads their jobs. */
    @PostMapping("/import-startup-map")
    public ResponseEntity<JobsStatusDto> importStartupMap() {
        return started(runner.startImportStartupMap());
    }

    /** Retries feed detection for companies still PENDING. */
    @PostMapping("/detect")
    public ResponseEntity<JobsStatusDto> detect() {
        return started(runner.startDetect());
    }

    /** Re-reads every ACTIVE company's feed now (it also runs daily). */
    @PostMapping("/refresh")
    public ResponseEntity<JobsStatusDto> refresh() {
        return started(runner.startRefresh());
    }

    /** Re-measures market demand from the stored jobs and updates the EMA skill weights (it also runs daily after the refresh). */
    @PostMapping("/market-demand")
    public ResponseEntity<JobsStatusDto> marketDemand() {
        return started(runner.startMarketDemand());
    }

    /** Re-extracts every job's skills (after the ML service's skill extractor changed). */
    @PostMapping("/reextract-skills")
    public ResponseEntity<JobsStatusDto> reextractSkills() {
        return started(runner.startReextractSkills());
    }

    @GetMapping("/status")
    public JobsStatusDto status() {
        return new JobsStatusDto(runner.status(),
                companies.countByStatus(CompanyStatus.ACTIVE),
                companies.countByStatus(CompanyStatus.PENDING),
                companies.countByStatus(CompanyStatus.UNSUPPORTED),
                postings.countByActiveTrue());
    }

    @GetMapping("/companies")
    public List<CompanyDto> companies(@RequestParam(defaultValue = "ACTIVE") CompanyStatus status) {
        return companies.findByStatusOrderByNameAsc(status).stream()
                .map(company -> CompanyDto.of(company, postings.countByCompanyAndActiveTrue(company)))
                .toList();
    }

    /** Adds one company and looks for its job feed straight away (a few seconds). */
    @PostMapping("/companies")
    public CompanyDto addCompany(@Valid @RequestBody AddCompanyRequest request) {
        Company company = companyService.add(request.name(), request.website(), request.careersUrl(), CompanySource.ADMIN);
        return CompanyDto.of(company, postings.countByCompanyAndActiveTrue(company));
    }

    private ResponseEntity<JobsStatusDto> started(boolean started) {
        return ResponseEntity.status(started ? HttpStatus.ACCEPTED : HttpStatus.CONFLICT).body(status());
    }
}
