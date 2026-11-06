package com.resumeanalyser.job;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** Reading the startup map's public pages: the sitemap, and a company page's schema.org data and Apply links. */
class StartupMapSourceTest {

    private final StartupMapSource source = new StartupMapSource(null, new ObjectMapper());

    @Test
    void sitemap_keepsOnlyCompanyPages() {
        String sitemap = """
                <urlset><url><loc>https://www.bangalorestartupmap.com/</loc></url>
                <url><loc>https://www.bangalorestartupmap.com/company/acceldata</loc></url>
                <url><loc> https://www.bangalorestartupmap.com/company/cred </loc></url>
                <url><loc>https://www.bangalorestartupmap.com/startups/fintech</loc></url></urlset>
                """;

        assertThat(StartupMapSource.companyPages(sitemap)).containsExactly(
                "https://www.bangalorestartupmap.com/company/acceldata",
                "https://www.bangalorestartupmap.com/company/cred");
    }

    @Test
    void companyPage_givesNameWebsiteAndApplyLinks() {
        String html = """
                <html><head><title>Acceldata — Bangalore Startup Map</title>
                <script type="application/ld+json">{"@context":"https://schema.org","@type":"BreadcrumbList"}</script>
                <script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization",
                  "name":"Acceldata","url":"https://www.acceldata.io","foundingDate":"2018"}</script></head>
                <body><a href="https://www.acceldata.io">Visit website ↗</a>
                <a class="btn" href="https://jobs.lever.co/acceldata/6f07801a">Apply<!-- --> ↗</a>
                <a href="https://jobs.lever.co/acceldata/d3410611"><span>Apply ↗</span></a>
                <a href="https://www.linkedin.com/company/acceldata">LinkedIn</a></body></html>
                """;

        var company = source.parse("https://www.bangalorestartupmap.com/company/acceldata", html).orElseThrow();

        assertThat(company.name()).isEqualTo("Acceldata");
        assertThat(company.website()).isEqualTo("https://www.acceldata.io");
        assertThat(company.applyLinks()).containsExactly(
                "https://jobs.lever.co/acceldata/6f07801a", "https://jobs.lever.co/acceldata/d3410611");
    }

    @Test
    void aPageWithoutOrganizationData_isSkipped() {
        assertThat(source.parse("https://x/company/y", "<html><title>Nothing</title></html>")).isEmpty();
    }

    @Test
    void toolName_isTheHiringToolsDomain() {
        assertThat(CompanyService.toolName("https://accenture.wd103.myworkdayjobs.com/en-US/x/job/1")).isEqualTo("myworkdayjobs.com");
        assertThat(CompanyService.toolName("https://astpl.keka.com/careers/jobdetails/1")).isEqualTo("keka.com");
    }
}
