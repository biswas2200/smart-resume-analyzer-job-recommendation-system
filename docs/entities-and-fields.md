# Entities and fields: code and descriptions

The implementation-level companion to [Class Diagram](class-diagram.md) and [Database Schema](database-schema.md): the code for every entity and model in the system, with each field described. Part 1 is the ML service's Pydantic contracts (`ml-service/app/models/schemas.py`), with the planned additions for the editions work called out. Part 2 is the backend's JPA entities (`backend/src/main/java/com/resumeanalyser/`), matching the Flyway `V1` schema field for field.

## Part 1: ML service Pydantic models (implemented)

Source: `ml-service/app/models/schemas.py`. These are the exact request/response contracts of the running `/parse`, `/match`, `/ats-score`, and `/analyze` endpoints today.

### 1.1 `ExperienceEntry`

```python
class ExperienceEntry(BaseModel):
    title: str
    organization: str = ""
    duration: str = ""
    description: str = ""
```

| Field | Type | Default | Description |
|---|---|---|---|
| `title` | `str` | *required* | Job title as extracted from the resume, e.g. `"Backend Engineer"`. |
| `organization` | `str` | `""` | Employer/organization name. Empty when the resume text didn't clearly state one. |
| `duration` | `str` | `""` | Free-text duration as written in the resume (e.g. `"2022-2024"`). It is deliberately not parsed into start/end dates yet, so the LLM can't invent dates that aren't there. |
| `description` | `str` | `""` | Free-text description of the role/responsibilities. |

### 1.2 `EducationEntry`

```python
class EducationEntry(BaseModel):
    degree: str
    institution: str = ""
    year: str = ""
```

| Field | Type | Default | Description |
|---|---|---|---|
| `degree` | `str` | *required* | Degree name, e.g. `"B.S. Computer Science"`. |
| `institution` | `str` | `""` | Institution name. |
| `year` | `str` | `""` | Free-text year/graduation date as written in the resume. |

### 1.3 `ResumeProfile`

```python
class ResumeProfile(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
```

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | `""` | Candidate's full name as extracted by `parser.py`: the local NER model by default, or the LLM if `PARSER_BACKEND=llm`. |
| `email` | `str` | `""` | Contact email extracted from the resume. This is separate from `ats_score.py`'s own email regex check; different modules compute the two for different purposes. |
| `phone` | `str` | `""` | Contact phone number, as written. |
| `skills` | `list[str]` | `[]` | Raw, extracted skill strings, not yet normalized. Normalization happens downstream in `normalizer.py` before matching. |
| `experience` | `list[ExperienceEntry]` | `[]` | Work history entries, in the order extracted. |
| `education` | `list[EducationEntry]` | `[]` | Education entries, in the order extracted. |

### 1.4 Request models

```python
class ParseRequest(BaseModel):
    resume_text: str

class MatchRequest(BaseModel):
    skills: list[str]
    top_n: int = 5

class AtsScoreRequest(BaseModel):
    resume_text: str
    target_keywords: list[str] = Field(default_factory=list)

class AnalyzeRequest(BaseModel):
    resume_text: str
    top_n: int = 3
    explainer: Literal["template", "llm"] = "template"   # planned, step 1
```

| Model | Field | Type | Default | Description |
|---|---|---|---|---|
| `ParseRequest` | `resume_text` | `str` | *required* | Raw resume text to extract a profile from. |
| `MatchRequest` | `skills` | `list[str]` | *required* | Raw or already-normalized skill strings to match against curated roles. |
| `MatchRequest` | `top_n` | `int` | `5` | Number of top-ranked roles to return. |
| `AtsScoreRequest` | `resume_text` | `str` | *required* | Raw resume text to score. |
| `AtsScoreRequest` | `target_keywords` | `list[str]` | `[]` | Optional keywords (e.g. from a target JD) to check coverage against; adds the `keyword_coverage` check and +20.0 to `max_score` only when non-empty. |
| `AnalyzeRequest` | `resume_text` | `str` | *required* | Raw resume text to run the full pipeline against. |
| `AnalyzeRequest` | `top_n` | `int` | `3` | Number of top role matches to include in the response. |
| `AnalyzeRequest` | `explainer` *(planned)* | `"template" \| "llm"` | `"template"` | Which explanation backend to use. The analysis pipeline uses `"llm"` for every account and falls back to the template when the AI engine is unavailable (FR-5.4, FR-12.2). |

### 1.5 `RoleMatch` and `MatchResponse`

```python
class RoleMatch(BaseModel):
    role: str
    score: float
    matched_skills: list[str]
    missing_skills: list[str]

class MatchResponse(BaseModel):
    matches: list[RoleMatch]
```

| Field | Type | Description |
|---|---|---|
| `RoleMatch.role` | `str` | Role title from the curated dataset, e.g. `"Backend Software Engineer"`. |
| `RoleMatch.score` | `float` | Cosine similarity between candidate and role skill vectors. Today rounded to 4 decimals after sorting. Planned for step 1: rounded to 2 decimals before sorting, with ties broken by role name, so ranking is identical across CPU architectures (FR-3.5). |
| `RoleMatch.matched_skills` | `list[str]` | Role-required skills the candidate's normalized skill set contains. |
| `RoleMatch.missing_skills` | `list[str]` | Role-required skills the candidate's normalized skill set does not contain. This is the exact input to `gap_analysis.py`. |
| `MatchResponse.matches` | `list[RoleMatch]` | Sorted descending by `score`, truncated to the requested `top_n`. |

### 1.6 `AtsCheck` and `AtsScoreResponse`

```python
class AtsCheck(BaseModel):
    name: str
    passed: bool
    detail: str

class AtsScoreResponse(BaseModel):
    score: float
    max_score: float
    checks: list[AtsCheck]
```

| Field | Type | Description |
|---|---|---|
| `AtsCheck.name` | `str` | Stable identifier for the check, e.g. `"contact_email"`, `"section_experience"`, `"keyword_coverage"`; see [LLD §5](lld.md#5-ats-scoring-rubric) for the full rubric. |
| `AtsCheck.passed` | `bool` | Whether this individual check passed. |
| `AtsCheck.detail` | `str` | Human-readable explanation, e.g. `"142 words (minimum 150)"`. |
| `AtsScoreResponse.score` | `float` | Total earned points across all checks, rounded to 2 decimals. |
| `AtsScoreResponse.max_score` | `float` | Total possible points: 90.0 normally, or 110.0 when `target_keywords` was supplied. |
| `AtsScoreResponse.checks` | `list[AtsCheck]` | One entry per rubric item, always in the same order they were evaluated. |

### 1.7 `GapAnalysis` and `AnalyzeResponse`

```python
class GapAnalysis(BaseModel):
    role: str
    missing_skills: list[str]

class EngineFingerprint(BaseModel):          # planned, step 1
    engine_version: str
    ner_model_sha: str
    vectors_sha: str
    taxonomy_sha: str
    weights_snapshot_id: str

class AnalyzeResponse(BaseModel):
    profile: ResumeProfile
    ats_score: AtsScoreResponse
    matches: list[RoleMatch]
    gaps: list[GapAnalysis]
    explanation: str
    explanation_source: Literal["template", "llm"] = "template"   # planned, step 1
    engine_fingerprint: EngineFingerprint | None = None            # planned, step 1
```

| Field | Type | Description |
|---|---|---|
| `GapAnalysis.role` | `str` | Role this gap breakdown applies to, one entry per role in `matches`. |
| `GapAnalysis.missing_skills` | `list[str]` | Copied directly from the corresponding `RoleMatch.missing_skills` (see `gap_analysis.py`; it is derived, not computed separately). |
| `AnalyzeResponse.profile` | `ResumeProfile` | The parsed candidate profile. |
| `AnalyzeResponse.ats_score` | `AtsScoreResponse` | The full ATS breakdown. |
| `AnalyzeResponse.matches` | `list[RoleMatch]` | Top-N ranked role matches. |
| `AnalyzeResponse.gaps` | `list[GapAnalysis]` | Gap breakdown, one per matched role. |
| `AnalyzeResponse.explanation` | `str` | Coaching text summarizing all of the above. Today it is always LLM-generated; after step 1, the deterministic template by default and LLM prose only when `explainer="llm"`. |
| `AnalyzeResponse.explanation_source` *(planned)* | `"template" \| "llm"` | Which backend produced `explanation`; also set to `"template"` when an LLM call failed and the template was used as fallback (NFR-3.1). |
| `AnalyzeResponse.engine_fingerprint` *(planned)* | `EngineFingerprint` | Engine version plus content hashes of the NER model, vector tables, taxonomy and weights snapshot. Identical fingerprints mean identical results across editions (FR-11.2, FR-11.3). Also returned by `GET /health`. |

## Part 2: backend JPA entities (Java / Spring Boot, implemented)

Source: `backend/src/main/java/com/resumeanalyser/`. Uses `jakarta.persistence` (Spring Boot 3.3) and Lombok. The listings below are abridged to the persistent fields; see the source files for Javadoc and relationship annotations. Schema is validated at startup against the Flyway migration (`ddl-auto: validate`).

### 2.1 `User`

Lives in its own `account` module rather than `auth`: `account` owns the identity/credential data (this entity), while `auth` (JWT issuance/validation and Spring Security config; see [LLD §7](lld.md#7-backend-module-design-implemented)) is the stateless module that operates on it. Keeping them separate means the security-config module has no persistence code of its own.

```java
package com.resumeanalyser.account;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "users")
@Getter
@Setter
public class User {

    @Id
    @GeneratedValue
    private UUID id;                       // Primary key.

    @Column(nullable = false, unique = true, length = 320)
    private String email;                  // Login identifier; unique across all users.

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;           // Bcrypt hash only — NFR-2.2: never store plaintext.

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private UserRole role = UserRole.USER;  // RBAC role; USER by default, mutable (USER <-> ADMIN).

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();  // Account creation timestamp.
}

public enum UserRole {
    USER, ADMIN
}
```

It is named `UserRole` instead of `Role` because `com.resumeanalyser.recommendation.Role` already means "job role" (e.g. "Backend Software Engineer") elsewhere in this schema; reusing the name for RBAC would collide conceptually even though the packages differ.

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Primary key, DB-generated. |
| `email` | `String` | Unique login identifier. |
| `passwordHash` | `String` | Salted bcrypt hash (NFR-2.2); plaintext is never persisted or logged. |
| `role` | `UserRole` | `USER` or `ADMIN`. Stored as `EnumType.STRING` (not `ORDINAL`) so inserting a new role later can't silently reshuffle existing rows' values. Defaults to `USER` at registration and can change later: an administrator can promote an account to `ADMIN`. `UserDetailsServiceImpl` reads this fresh from the DB on every request (via `JwtAuthenticationFilter`), so a role change takes effect on the user's very next request, not just after their token is reissued. |
| `createdAt` | `Instant` | Set once at creation, immutable thereafter. |

### 2.2 `Resume`

```java
package com.resumeanalyser.resume;

import com.resumeanalyser.account.User;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "resumes", uniqueConstraints = @UniqueConstraint(columnNames = {"user_id", "version"}))
@Getter
@Setter
public class Resume {

    @Id
    @GeneratedValue
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;                     // Owning candidate.

    @Column(name = "file_ref", nullable = false, columnDefinition = "TEXT")
    private String fileRef;                // Object-storage key/URL; the file itself is not stored in Postgres.

    @Column(nullable = false)
    private int version;                   // Monotonically increasing per user — FR-1.5: never overwritten.

    @Column(name = "uploaded_at", nullable = false, updatable = false)
    private Instant uploadedAt = Instant.now();
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Primary key. |
| `user` | `User` | Owning candidate (many resumes per user). |
| `fileRef` | `String` | Pointer to the stored file (object storage), not the file bytes themselves. |
| `version` | `int` | Increasing per-user version number, implementing FR-1.5 (retain every upload as a distinct version). |
| `uploadedAt` | `Instant` | Upload timestamp. |

### 2.3 `ParsedProfile`

```java
package com.resumeanalyser.resume;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "parsed_profiles")
@Getter
@Setter
public class ParsedProfile {

    @Id
    @GeneratedValue
    private UUID id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "resume_id", nullable = false, unique = true)
    private Resume resume;                 // One profile per resume version.

    @Column(nullable = false)
    private String name = "";              // Mirrors ResumeProfile.name in the ML service contract.

    @Column(nullable = false)
    private String email = "";

    @Column(nullable = false)
    private String phone = "";

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false)
    private List<String> skills;           // Raw extracted skills — normalization happens at match time, not storage time.

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false)
    private List<ExperienceEntry> experience;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false)
    private List<EducationEntry> education;

    // Output of the same /analyze-file call, persisted so the dashboard never re-calls the ML service.
    @Column(name = "ats_score", nullable = false)
    private double atsScore;

    @Column(name = "ats_max_score", nullable = false)
    private double atsMaxScore;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "ats_checks", nullable = false)
    private List<AtsCheckEntry> atsChecks;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String explanation = "";

    // Embeddable nested shapes, matching ml-service's Pydantic models field-for-field.
    public record ExperienceEntry(String title, String organization, String duration, String description) {}
    public record EducationEntry(String degree, String institution, String year) {}
    public record AtsCheckEntry(String name, boolean passed, String detail) {}
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Primary key. |
| `resume` | `Resume` | The resume version this profile was extracted from (1:1). |
| `name`, `email`, `phone` | `String` | Contact fields, field-for-field identical to `ResumeProfile` in `ml-service`. |
| `skills` | `List<String>` | Stored as JSONB: raw extracted skills, before normalization. |
| `experience` | `List<ExperienceEntry>` | Stored as JSONB; nested record mirrors `ExperienceEntry` in Part 1. |
| `education` | `List<EducationEntry>` | Stored as JSONB; nested record mirrors `EducationEntry` in Part 1. |
| `atsScore`, `atsMaxScore` | `double` | Copied from `AtsScoreResponse` at upload time. |
| `atsChecks` | `List<AtsCheckEntry>` | JSONB; mirrors `AtsCheck` in Part 1. |
| `explanation` | `String` | The explanation returned by the ML service for this version (template or LLM; `explanation_source` and `engine_fingerprint` columns are planned for step 1). |

### 2.4 `Role`

```java
package com.resumeanalyser.recommendation;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import java.util.UUID;

@Entity
@Table(name = "roles")
@Getter
@Setter
public class Role {

    @Id
    @GeneratedValue
    private UUID id;

    @Column(nullable = false, unique = true)
    private String title;                  // e.g. "Backend Software Engineer" — matches role_skills.json's "role" key.

    @Column(nullable = false, columnDefinition = "TEXT")
    private String description = "";       // Not present in role_skills.json today; new field for the DB-backed dataset.
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Primary key. |
| `title` | `String` | Unique role name; the DB-backed replacement for a `role_skills.json` entry's `"role"` field. |
| `description` | `String` | Free-text role description for the dashboard. The flat-file dataset has no equivalent field. |

### 2.5 `SkillVector`

```java
package com.resumeanalyser.skillvector;

import com.resumeanalyser.recommendation.Role;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "skill_vectors")
@Getter
@Setter
public class SkillVector {

    @Id
    @GeneratedValue
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "role_id", nullable = false)
    private Role role;

    @Column(nullable = false)
    private String skill;                  // Canonical skill name — matches skill_taxonomy.json's canonical keys.

    @Column(nullable = false)
    private double weight;                 // EMA-updated weight (FR-7.2): new = α·signal + (1-α)·old.

    @Column(name = "version_timestamp", nullable = false)
    private Instant versionTimestamp = Instant.now();  // FR-7.1: every weight is versioned, never mutated in place.

    @Column(nullable = false)
    private boolean current = true;        // Fast lookup flag for "the active version" — see database-schema.md idx_skill_vectors_current.
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Primary key. |
| `role` | `Role` | Role this weighted skill belongs to. |
| `skill` | `String` | Canonical skill name. |
| `weight` | `double` | Current EMA-computed weight. It replaces the implicit "every skill weighted equally" assumption in today's `matcher.py`. |
| `versionTimestamp` | `Instant` | When this version was written. Every EMA update inserts a new row instead of changing this one (FR-7.4). |
| `current` | `boolean` | `true` for exactly one row per `(role, skill)` at a time; that is the row `/match` reads. |

### 2.6 `Recommendation`

```java
package com.resumeanalyser.recommendation;

import com.resumeanalyser.account.User;
import com.resumeanalyser.resume.Resume;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "recommendations")
@Getter
@Setter
public class Recommendation {

    @Id
    @GeneratedValue
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "role_id", nullable = false)
    private Role role;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "resume_id", nullable = false)
    private Resume resume;                 // The analysis run (resume version) that produced this row.

    @Column(name = "match_score", nullable = false)
    private double matchScore;             // Cosine similarity from RoleMatch.score, persisted for history/trend (FR-6.2).

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "matched_skills", nullable = false)
    private List<String> matchedSkills;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "missing_skills", nullable = false)
    private List<String> missingSkills;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Primary key. |
| `user` | `User` | Candidate this recommendation was made for. |
| `role` | `Role` | The recommended role. |
| `resume` | `Resume` | The resume version whose analysis produced this recommendation, so the dashboard reads "this version's recommendations" directly. |
| `matchScore` | `double` | Persisted copy of the ML service's `RoleMatch.score` at computation time. |
| `matchedSkills`, `missingSkills` | `List<String>` | JSONB copies of `RoleMatch.matched_skills` / `missing_skills`. |
| `createdAt` | `Instant` | When this recommendation was generated; used by the version/score trend view (FR-6.2). |

### 2.7 `Feedback`

```java
package com.resumeanalyser.feedback;

import com.resumeanalyser.recommendation.Recommendation;
import com.resumeanalyser.skillvector.SkillVector;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "feedback")
@Getter
@Setter
public class Feedback {

    @Id
    @GeneratedValue
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "recommendation_id", nullable = false)
    private Recommendation recommendation;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "skill_vector_version_id")
    private SkillVector skillVectorVersion;   // FR-10.2: the specific weight-vector version active when feedback was given.

    @Column(nullable = false)
    private boolean helpful;                  // "helpful" / "not helpful" — FR-10.1.

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Primary key. |
| `recommendation` | `Recommendation` | The specific recommendation this feedback is about. |
| `skillVectorVersion` | `SkillVector` | The exact skill-vector version active at feedback time. It makes the EMA update auditable (FR-10.2), and is nullable so historical feedback survives if the referenced version is later purged. |
| `helpful` | `boolean` | `true` = helpful, `false` = not helpful. |
| `createdAt` | `Instant` | Feedback timestamp. |

## Related documents

- [Class Diagram](class-diagram.md) · [Database Schema](database-schema.md) · [LLD](lld.md) · [Editions & Parity](editions-and-parity.md)
