package com.resumeanalyser.job;

import com.resumeanalyser.job.feed.JobFeedException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import java.net.URI;
import java.time.Clock;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

/**
 * The company list: seeding it from Wikidata, adding one company by hand,
 * and finding each company's job feed ({@link AtsDetector}). A company whose
 * feed is found becomes ACTIVE and its jobs are stored at once.
 */
@Service
public class CompanyService {

    private static final Logger log = LoggerFactory.getLogger(CompanyService.class);

    private final CompanyRepository companies;
    private final WikidataCompanySource wikidata;
    private final StartupMapSource startupMap;
    private final AtsDetector detector;
    private final JobPostingWriter writer;
    private final Throttle throttle;
    private final JobsProperties properties;
    private final Clock clock;

    public CompanyService(CompanyRepository companies, WikidataCompanySource wikidata, StartupMapSource startupMap,
                          AtsDetector detector, JobPostingWriter writer, Throttle throttle,
                          JobsProperties properties, Clock clock) {
        this.companies = companies;
        this.wikidata = wikidata;
        this.startupMap = startupMap;
        this.throttle = throttle;
        this.detector = detector;
        this.writer = writer;
        this.properties = properties;
        this.clock = clock;
    }

    public record SeedSummary(int fromWikidata, int added, int alreadyKnown, int badWebsite) {
        @Override
        public String toString() {
            return "%d companies from Wikidata: %d added, %d already known, %d without a usable website"
                    .formatted(fromWikidata, added, alreadyKnown, badWebsite);
        }
    }

    public record DetectSummary(int checked, int active, int unsupported, int failed, int jobsInCity) {
        @Override
        public String toString() {
            return "%d companies checked: %d with a job feed, %d without, %d to retry; %d open jobs in the city"
                    .formatted(checked, active, unsupported, failed, jobsInCity);
        }
    }

    /** Adds every Bengaluru company Wikidata knows that we don't have yet, as PENDING. */
    public SeedSummary seedFromWikidata() {
        List<WikidataCompanySource.WikidataCompany> found = wikidata.bengaluruCompanies();
        int added = 0;
        int known = 0;
        int bad = 0;
        for (WikidataCompanySource.WikidataCompany item : found) {
            String domain = Domains.normalize(item.website());
            if (domain == null) {
                bad++;
                continue;
            }
            if (companies.findByDomain(domain).isPresent()) {
                known++;
                continue;
            }
            Company company = new Company();
            company.setName(item.name());
            company.setDomain(domain);
            company.setCity(properties.city());
            company.setSource(CompanySource.WIKIDATA);
            company.setWikidataId(item.wikidataId());
            companies.save(company);
            added++;
        }
        SeedSummary summary = new SeedSummary(found.size(), added, known, bad);
        log.info("Wikidata seed: {}", summary);
        return summary;
    }

    /**
     * @param otherTools companies whose jobs are on a hiring tool we can't read yet, by tool host
     */
    public record ImportSummary(int pages, int added, int matchedExisting, int active, int jobsInCity,
                                Map<String, Long> otherTools, int noJobsLinked, int failed) {
        @Override
        public String toString() {
            String tools = otherTools.entrySet().stream()
                    .map(entry -> entry.getKey() + " " + entry.getValue())
                    .collect(Collectors.joining(", "));
            return ("%d startup map pages: %d companies added, %d already known; %d with a job feed (%d open jobs "
                    + "in the city); on tools we can't read yet: %s; %d with no job linked; %d failed")
                    .formatted(pages, added, matchedExisting, active, jobsInCity, tools.isEmpty() ? "none" : tools,
                            noJobsLinked, failed);
        }
    }

    /**
     * Adds the Bangalore Startup Map's companies and reads their jobs. A
     * company's Apply link names its hiring tool, so no guessing is needed:
     * a Lever, Greenhouse or Ashby link is read at once; any other tool is
     * recorded (careers URL kept) as not supported yet; a company with no
     * job linked is left without guessing, since most of those simply have
     * no openings.
     */
    public ImportSummary importStartupMap() {
        List<String> pages = startupMap.companyPages();
        int added = 0;
        int existing = 0;
        int active = 0;
        int inCity = 0;
        int noJobs = 0;
        int failed = 0;
        Map<String, Long> otherTools = new TreeMap<>();
        for (String page : pages) {
            throttle.pausePage();
            Optional<StartupMapSource.MapCompany> read;
            try {
                read = startupMap.read(page);
            } catch (IllegalStateException e) {
                failed++;
                log.warn("Startup map page failed: {}", e.getMessage());
                continue;
            }
            if (read.isEmpty() || Domains.normalize(read.get().website()) == null) {
                failed++;
                continue;
            }
            StartupMapSource.MapCompany item = read.get();
            String domain = Domains.normalize(item.website());
            Optional<Company> known = companies.findByDomain(domain);
            Company company = known.orElseGet(() -> {
                Company created = new Company();
                created.setName(item.name());
                created.setDomain(domain);
                created.setCity(properties.city());
                created.setSource(CompanySource.STARTUP_MAP);
                return created;
            });
            if (known.isPresent()) {
                existing++;
            } else {
                added++;
            }
            Optional<String> board = item.applyLinks().stream()
                    .filter(link -> AtsDetector.boardFromUrl(link).isPresent())
                    .findFirst();
            String careersUrl = board.orElse(item.applyLinks().isEmpty() ? null : item.applyLinks().get(0));
            if (careersUrl != null) {
                company.setCareersUrl(careersUrl);
            }
            if (company.getStatus() == CompanyStatus.ACTIVE) {
                companies.save(company);
                active++;
                continue;
            }
            if (board.isPresent()) {
                companies.save(company);
                try {
                    Optional<JobPostingWriter.Applied> applied = detect(company, board.get());
                    if (applied.isPresent()) {
                        active++;
                        inCity += applied.get().inCity();
                    }
                } catch (JobFeedException e) {
                    failed++;
                    company.setLastError(e.getMessage());
                    companies.save(company);
                }
                continue;
            }
            company.setStatus(CompanyStatus.UNSUPPORTED);
            company.setLastCheckedAt(clock.instant());
            if (careersUrl != null) {
                String tool = toolName(careersUrl);
                otherTools.merge(tool, 1L, Long::sum);
                company.setLastError("Jobs are on " + tool + ", which we can't read yet");
            } else {
                noJobs++;
                company.setLastError("No open job linked on the Bangalore Startup Map");
            }
            companies.save(company);
        }
        ImportSummary summary = new ImportSummary(pages.size(), added, existing, active, inCity, otherTools, noJobs, failed);
        log.info("Startup map import: {}", summary);
        return summary;
    }

    /** "accenture.wd103.myworkdayjobs.com" -> "myworkdayjobs.com"; "astpl.keka.com" -> "keka.com". */
    static String toolName(String url) {
        try {
            String host = URI.create(url).getHost();
            if (host == null) {
                return "unknown";
            }
            String[] parts = host.toLowerCase(Locale.ROOT).split("\\.");
            return parts.length <= 2 ? host : parts[parts.length - 2] + "." + parts[parts.length - 1];
        } catch (IllegalArgumentException e) {
            return "unknown";
        }
    }

    /** Looks for a job feed for every PENDING company. */
    public DetectSummary detectPending() {
        List<Company> pending = companies.findByStatusOrderByNameAsc(CompanyStatus.PENDING);
        int active = 0;
        int unsupported = 0;
        int failed = 0;
        int inCity = 0;
        for (Company company : pending) {
            try {
                Optional<JobPostingWriter.Applied> applied = detect(company, null);
                if (applied.isPresent()) {
                    active++;
                    inCity += applied.get().inCity();
                } else {
                    unsupported++;
                }
            } catch (JobFeedException e) {
                failed++;
                company.setLastError(e.getMessage());
                companies.save(company);
            }
        }
        DetectSummary summary = new DetectSummary(pending.size(), active, unsupported, failed, inCity);
        log.info("Job feed detection: {}", summary);
        return summary;
    }

    /**
     * Adds one company (or finds it by its website) and looks for its job
     * feed straight away -- the path the watchlist's "add a missing company"
     * will use.
     *
     * @throws IllegalArgumentException if the website isn't a web address
     */
    public Company add(String name, String website, String careersUrl, CompanySource source) {
        String domain = Domains.normalize(website);
        if (domain == null) {
            throw new IllegalArgumentException("Not a website address: " + website);
        }
        Company company = companies.findByDomain(domain).orElseGet(() -> {
            Company created = new Company();
            created.setName(name.trim());
            created.setDomain(domain);
            created.setCity(properties.city());
            created.setSource(source);
            return companies.save(created);
        });
        if (company.getStatus() != CompanyStatus.ACTIVE) {
            try {
                detect(company, careersUrl);
            } catch (JobFeedException e) {
                company.setLastError(e.getMessage());
                companies.save(company);
            }
        }
        return company;
    }

    /** Runs detection for one company and records the outcome; the postings are stored when a feed is found. */
    private Optional<JobPostingWriter.Applied> detect(Company company, String careersUrl) {
        Optional<AtsDetector.Detection> found = detector.detect(company.getName(), company.getDomain(), careersUrl);
        company.setLastCheckedAt(clock.instant());
        if (found.isEmpty()) {
            company.setStatus(CompanyStatus.UNSUPPORTED);
            company.setAtsProvider(null);
            company.setAtsSlug(null);
            company.setDetectedBy(null);
            company.setLastError(null);
            companies.save(company);
            writer.closeAll(company);
            return Optional.empty();
        }
        AtsDetector.Detection detection = found.get();
        company.setStatus(CompanyStatus.ACTIVE);
        company.setAtsProvider(detection.provider());
        company.setAtsSlug(detection.slug());
        company.setDetectedBy(detection.method());
        companies.save(company);
        log.info("Job feed found for {}: {} {} ({}), {} postings", company.getName(), detection.provider(),
                detection.slug(), detection.method(), detection.postings().size());
        return Optional.of(writer.apply(company, detection.postings()));
    }
}
