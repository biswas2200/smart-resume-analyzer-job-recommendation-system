"""Tests local_ner_parser.py -- the zero-external-API resume parsing
backend. Every test here works with hand-built NER entity lists or a fake
pipeline callable, so the suite never downloads or runs the real
yashpwr/resume-ner-bert model.
"""

from app.models.schemas import EducationEntry
import pytest

from app.services.local_ner_parser import (
    _align_education_to_lines,
    _chunk_text,
    _entities_to_profile,
    _extract_name,
    _fill_education_institutions,
    _fill_education_years,
    _widen_education_institutions,
    _with_source_text,
    parse_resume_local,
)


def _entity(entity_group: str, word: str) -> dict:
    """Build one fake pipeline-output row. start/end aren't used by any of
    the assembly logic under test, so they're left at 0.
    """
    return {"entity_group": entity_group, "word": word, "score": 0.99, "start": 0, "end": 0}


# --- Assembly (_entities_to_profile) --------------------------------------


def test_single_job_entry_groups_correctly():
    entities = [_entity("Designation", "Software Engineer"), _entity("Companies worked at", "Acme Corp")]

    profile = _entities_to_profile(entities, "Software Engineer at Acme Corp")

    assert len(profile.experience) == 1
    assert profile.experience[0].title == "Software Engineer"
    assert profile.experience[0].organization == "Acme Corp"
    assert profile.experience[0].duration == ""
    assert profile.experience[0].description == ""


def test_single_education_entry_groups_correctly():
    entities = [
        _entity("Degree", "B.Tech Computer Science"),
        _entity("College Name", "IIT Bombay"),
        _entity("Graduation Year", "2020"),
    ]

    profile = _entities_to_profile(entities, "B.Tech Computer Science, IIT Bombay, 2020")

    assert len(profile.education) == 1
    assert profile.education[0].degree == "B.Tech Computer Science"
    assert profile.education[0].institution == "IIT Bombay"
    assert profile.education[0].year == "2020"


def test_two_consecutive_jobs_split_into_two_entries():
    entities = [
        _entity("Designation", "Backend Engineer"),
        _entity("Companies worked at", "Acme Corp"),
        _entity("Designation", "Intern"),
        _entity("Companies worked at", "Widgets Inc"),
    ]

    profile = _entities_to_profile(entities, "irrelevant full text")

    assert [e.title for e in profile.experience] == ["Backend Engineer", "Intern"]
    assert [e.organization for e in profile.experience] == ["Acme Corp", "Widgets Inc"]


def test_resume_with_no_education_section_produces_empty_list():
    entities = [_entity("Designation", "Engineer"), _entity("Skills", "Python")]

    profile = _entities_to_profile(entities, "irrelevant full text")

    assert profile.education == []


def test_resume_with_no_experience_section_produces_empty_list():
    entities = [_entity("Degree", "B.Sc"), _entity("Skills", "Python")]

    profile = _entities_to_profile(entities, "irrelevant full text")

    assert profile.experience == []


def test_filler_without_anchor_is_dropped():
    # A stray "College Name" with no preceding "Degree" -- should not
    # produce a spurious EducationEntry with an empty degree.
    entities = [_entity("College Name", "IIT Bombay")]

    profile = _entities_to_profile(entities, "irrelevant full text")

    assert profile.education == []


def test_skills_span_with_commas_gets_split_and_normalized():
    entities = [_entity("Skills", "Python, SQL, Java")]

    profile = _entities_to_profile(entities, "irrelevant full text")

    assert profile.skills == ["Python", "SQL", "Java"]


def test_skills_span_with_slash_delimiter_gets_split():
    entities = [_entity("Skills", "HTML/CSS")]

    profile = _entities_to_profile(entities, "irrelevant full text")

    assert profile.skills == ["HTML", "CSS"]


def test_duplicate_experience_entries_from_chunk_overlap_are_deduped():
    # Simulates the same job appearing twice because it fell inside the
    # overlapping region of two adjacent chunks.
    entities = [
        _entity("Designation", "Engineer"),
        _entity("Companies worked at", "Acme Corp"),
        _entity("Designation", "Engineer"),
        _entity("Companies worked at", "Acme Corp"),
    ]

    profile = _entities_to_profile(entities, "irrelevant full text")

    assert len(profile.experience) == 1


def test_email_extracted_via_regex_takes_priority_over_ner_span():
    entities = [_entity("Email Address", "jane at example dot com")]
    full_text = "Contact: jane.doe@example.com for more info"

    profile = _entities_to_profile(entities, full_text)

    assert profile.email == "jane.doe@example.com"


def test_email_falls_back_to_ner_span_when_regex_finds_none():
    entities = [_entity("Email Address", "jane.doe@example.com")]
    full_text = "Contact: jane dot doe at example dot com"

    profile = _entities_to_profile(entities, full_text)

    assert profile.email == "jane.doe@example.com"


def test_phone_regex_reads_indian_numbers_written_in_two_groups_of_five():
    for written in ("+91 98765 43210", "98765-43210", "+91 9876543210", "9876543210"):
        profile = _entities_to_profile([], f"Priya Sharma\n{written} | Bengaluru")

        assert profile.phone == written


def test_phone_regex_still_reads_us_style_numbers_and_skips_years():
    assert _entities_to_profile([], "Call +1 (555) 123-4567").phone == "+1 (555) 123-4567"
    assert _entities_to_profile([], "B.Tech (2016 - 2020), Jun 2022 - Present").phone == ""


def test_experience_duration_filled_from_nearby_date_range():
    entities = [_entity("Designation", "Software Engineer"), _entity("Companies worked at", "Acme Corp")]
    full_text = "Software Engineer at Acme Corp, Jan 2020 - Mar 2022"

    profile = _entities_to_profile(entities, full_text)

    assert profile.experience[0].duration == "Jan 2020 - Mar 2022"


def test_experience_description_always_empty():
    entities = [_entity("Designation", "Engineer"), _entity("Companies worked at", "Acme Corp")]
    full_text = "Engineer at Acme Corp, Jan 2020 - Mar 2022. Built things."

    profile = _entities_to_profile(entities, full_text)

    assert profile.experience[0].description == ""


def test_unmapped_entity_groups_are_ignored():
    entities = [
        _entity("Years of Experience", "5 years"),
        _entity("Location", "Bengaluru"),
        _entity("UNKNOWN", "???"),
        _entity("Skills", "Python"),
    ]

    profile = _entities_to_profile(entities, "irrelevant full text")

    assert profile.skills == ["Python"]
    assert profile.education == []
    assert profile.experience == []


# --- Chunking (_chunk_text) ------------------------------------------------


def test_chunk_text_splits_long_text_into_overlapping_windows():
    long_text = " ".join(f"word{i}" for i in range(1000))

    chunks = _chunk_text(long_text, max_words=380, overlap_words=50)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.split()) <= 380
    # The tail of the first chunk should reappear at the head of the second,
    # proving the overlap actually happened.
    first_words = chunks[0].split()
    second_words = chunks[1].split()
    assert first_words[-50:] == second_words[:50]


def test_chunk_text_returns_single_chunk_for_short_text():
    short_text = "just a few words here"

    chunks = _chunk_text(short_text, max_words=380, overlap_words=50)

    assert chunks == [short_text]


# --- Routing/integration (parse_resume_local) ------------------------------


def test_parse_resume_local_merges_entities_across_chunks():
    calls: list[str] = []

    def fake_pipeline(chunk_text: str) -> list[dict]:
        calls.append(chunk_text)
        if len(calls) == 1:
            return [_entity("Designation", "Engineer")]
        return [_entity("Companies worked at", "Acme Corp")]

    long_text = " ".join(f"word{i}" for i in range(1000))

    profile = parse_resume_local(long_text, ner_pipeline=fake_pipeline)

    assert len(calls) > 1
    assert len(profile.experience) == 1
    assert profile.experience[0].title == "Engineer"
    assert profile.experience[0].organization == "Acme Corp"


# --- Sectioning + dictionary skills integration (FR-1.6/FR-1.7) -----------


def test_parse_resume_local_scopes_ner_to_experience_and_education_when_headings_present():
    seen_chunks: list[str] = []

    def fake_pipeline(chunk_text: str) -> list[dict]:
        seen_chunks.append(chunk_text)
        return []

    text = "\n".join(
        [
            "Jane Doe",
            "Skills",
            "Python, SQL",
            "Experience",
            "Backend Engineer at Acme Corp",
            "Education",
            "B.Tech Computer Science, IIT Bombay",
        ]
    )

    parse_resume_local(text, ner_pipeline=fake_pipeline)

    combined = " ".join(seen_chunks)
    assert "Backend Engineer" in combined
    assert "IIT Bombay" in combined
    # The Skills section and the un-sectioned "Jane Doe" line must not reach
    # the NER model at all once real headings are present -- dictionary
    # matching covers skills instead (see the merge test below).
    assert "Jane Doe" not in combined
    assert "Python, SQL" not in combined


def test_parse_resume_local_falls_back_to_whole_text_when_no_headings_are_recognized():
    seen_chunks: list[str] = []

    def fake_pipeline(chunk_text: str) -> list[dict]:
        seen_chunks.append(chunk_text)
        return []

    text = "Jane Doe, Backend Engineer at Acme Corp, Python and SQL."

    parse_resume_local(text, ner_pipeline=fake_pipeline)

    assert " ".join(seen_chunks) == text


# --- Graduation year fallback (_fill_education_years) ---------------------
# The NER model is weak at "Graduation Year" on real resumes (21% token F1
# across 220 resumes, see ml-service/scripts/evaluate_ner_extraction.py); this regex fallback exists
# to fill that gap entirely, not to refine an existing signal.


def test_fill_education_years_fills_a_single_entry_from_the_section_text():
    education = [EducationEntry(degree="B.Sc", institution="", year="")]

    result = _fill_education_years(education, "B.Sc Physics\n\nSome College\n\n2019")

    assert result[0].year == "2019"


def test_fill_education_years_assigns_years_positionally_across_multiple_entries():
    education = [
        EducationEntry(degree="PG-DAC", institution="", year=""),
        EducationEntry(degree="B.E", institution="", year=""),
    ]

    result = _fill_education_years(education, "PG-DAC\n\nCDAC ACTS\n\n2017\n\nB.E\n\nSome University\n\n2016")

    assert result[0].year == "2017"
    assert result[1].year == "2016"


def test_fill_education_years_does_not_overwrite_an_entry_that_already_has_a_year():
    education = [EducationEntry(degree="B.Sc", institution="", year="2015")]

    result = _fill_education_years(education, "B.Sc Physics\n\n2019")

    assert result[0].year == "2015"


def test_fill_education_years_leaves_entries_unfilled_when_no_year_is_present():
    education = [EducationEntry(degree="B.Sc", institution="", year="")]

    result = _fill_education_years(education, "B.Sc Physics with no year mentioned anywhere")

    assert result[0].year == ""


def test_fill_education_years_is_a_noop_for_empty_section_text():
    education = [EducationEntry(degree="B.Sc", institution="", year="")]

    result = _fill_education_years(education, "")

    assert result[0].year == ""


def test_fill_education_years_ignores_extra_years_beyond_the_entry_count():
    education = [EducationEntry(degree="B.Sc", institution="", year="")]

    result = _fill_education_years(education, "B.Sc\n\n2019\n\nSome unrelated later year 2021")

    assert result[0].year == "2019"


def test_parse_resume_local_fills_graduation_year_end_to_end_when_ner_never_predicts_one():
    def fake_pipeline(chunk_text: str) -> list[dict]:
        # Simulates the real model's behavior: it emits a Degree anchor but
        # -- as is common on real resumes -- no Graduation Year entity.
        return [_entity("Degree", "B.Sc Physics")]

    text = "\n".join(["Education", "B.Sc Physics", "Some College", "2019"])

    profile = parse_resume_local(text, ner_pipeline=fake_pipeline)

    assert len(profile.education) == 1
    assert profile.education[0].year == "2019"


def test_parse_resume_local_merges_dictionary_skills_with_ner_detected_skills():
    def fake_pipeline(chunk_text: str) -> list[dict]:
        return [_entity("Skills", "Kubernetes")]

    # "Python" only appears in a Skills section a headings-based NER pass
    # would never see (see the scoping test above); dictionary_skills.py
    # finds it anyway since it scans the whole resume text.
    text = "\n".join(["Skills", "Python", "Experience", "Engineer at Acme Corp"])

    profile = parse_resume_local(text, ner_pipeline=fake_pipeline)

    assert "Python" in profile.skills
    assert "Kubernetes" in profile.skills


# --- Low-confidence entities ---------------------------------------------


def test_entities_below_min_score_are_dropped():
    entities = [
        _entity("Designation", "Software Engineer"),
        {"entity_group": "Degree", "word": "the", "score": 0.45, "start": 0, "end": 0},
        {"entity_group": "Companies worked at", "word": "with", "score": 0.5, "start": 0, "end": 0},
    ]

    profile = _entities_to_profile(entities, "Software Engineer", min_score=0.6)

    assert profile.education == []
    assert [(e.title, e.organization) for e in profile.experience] == [("Software Engineer", "")]


def test_default_min_score_keeps_low_confidence_entities():
    # The measured default is 0.0: with per-word aggregation the
    # low-confidence tail is mostly real titles/companies (see _MIN_ENTITY_SCORE).
    entities = [{"entity_group": "Designation", "word": "Line Cook", "score": 0.41, "start": 0, "end": 0}]

    profile = _entities_to_profile(entities, "Line Cook")

    assert [e.title for e in profile.experience] == ["Line Cook"]


# --- Chunking keeps line breaks ----------------------------------------------


def test_chunk_text_keeps_newlines_inside_chunks():
    long_text = "\n".join(f"line{i} word" for i in range(500))

    chunks = _chunk_text(long_text, max_words=380, overlap_words=50)

    assert len(chunks) > 1
    assert chunks[0].startswith("line0 word\nline1 word\n")
    assert "\n" in chunks[1]


# --- Name (_extract_name) ------------------------------------------------------


def test_extract_name_takes_the_first_line_when_it_looks_like_a_name():
    assert _extract_name("Abhishek Jha\nApplication Development Associate - Accenture") == "Abhishek Jha"


def test_extract_name_accepts_all_caps_and_accented_names():
    assert _extract_name("  JOHN   SMITH  \nBackend Engineer") == "JOHN SMITH"
    assert _extract_name("José García\nMadrid") == "José García"


def test_extract_name_skips_title_lines_and_headings():
    assert _extract_name("Curriculum Vitae\nPriya Sharma\npriya@example.com") == "Priya Sharma"
    assert _extract_name("Senior Software Engineer\nExperience\nAcme") == ""


def test_extract_name_rejects_lines_with_digits_or_email():
    assert _extract_name("priya@example.com\n+91 98765 43210\nPune, India") == ""


def test_parse_resume_local_finds_the_name_even_when_ner_only_sees_sections():
    text = "\n".join(["Jane Doe", "Experience", "Backend Engineer at Acme Corp"])

    profile = parse_resume_local(text, ner_pipeline=lambda chunk: [])

    assert profile.name == "Jane Doe"


# --- Institution fallback (_fill_education_institutions) ------------------------


def test_fill_education_institutions_takes_the_institution_line():
    education = [EducationEntry(degree="B.E in Information Science", institution="", year="")]

    result = _fill_education_institutions(
        education, "B.E in Information Science\nB.v.b college of engineering and technology\n2013 to 2017"
    )

    assert result[0].institution == "B.v.b college of engineering and technology"


def test_fill_education_institutions_keeps_only_the_institution_part_of_a_line():
    education = [EducationEntry(degree="B.Tech", institution="", year="")]

    result = _fill_education_institutions(education, "B.Tech, Anna University, Chennai")

    assert result[0].institution == "Anna University"


def test_fill_education_institutions_splits_on_full_width_dash_and_colon():
    education = [EducationEntry(degree="Bachelor of Science", institution="", year="")]

    result = _fill_education_institutions(
        education, "Master of Arts : Computer Graphics\nWSSS COLLEGE in Suwalki － City , State , Poland"
    )

    assert result[0].institution == "WSSS COLLEGE in Suwalki"


def test_fill_education_institutions_trims_an_institution_folded_into_the_degree():
    education = [
        EducationEntry(
            degree="Bachelor of Engg in Information Technology Shivaji University Kolhapur", institution="", year=""
        )
    ]

    result = _fill_education_institutions(
        education, "Bachelor of Engg in Information Technology\nShivaji University Kolhapur\n2017"
    )

    assert result[0].institution == "Shivaji University Kolhapur"
    assert result[0].degree == "Bachelor of Engg in Information Technology"


def test_fill_education_institutions_assigns_positionally_and_keeps_existing_values():
    education = [
        EducationEntry(degree="M.Tech", institution="IIT Bombay", year=""),
        EducationEntry(degree="B.Tech", institution="", year=""),
    ]

    result = _fill_education_institutions(education, "M.Tech\nNIT Trichy\nB.Tech\nPSG College of Technology")

    assert result[0].institution == "IIT Bombay"
    assert result[1].institution == "NIT Trichy"


def test_fill_education_institutions_ignores_words_that_only_contain_a_keyword():
    education = [EducationEntry(degree="B.Sc", institution="", year="")]

    result = _fill_education_institutions(education, "B.Sc\nschooling completed in 2015")

    assert result[0].institution == ""


# --- Institution names cut short by the model (_widen_education_institutions) -------


@pytest.mark.parametrize("tagged", ["University", "Pune University", "Phule Pune University"])
def test_widen_restores_the_start_of_a_cut_institution(tagged):
    education = [EducationEntry(degree="B.Tech in Computer Science", institution=tagged, year="2022")]

    result = _widen_education_institutions(
        education, "B.Tech in Computer Science, Savitribai Phule Pune University, 2022"
    )

    assert result[0].institution == "Savitribai Phule Pune University"


def test_widen_keeps_an_institution_that_is_already_whole():
    education = [EducationEntry(degree="B.Tech", institution="Anna University", year="")]

    result = _widen_education_institutions(education, "B.Tech, Anna University, Chennai")

    assert result[0].institution == "Anna University"


def test_widen_does_not_pull_in_a_degree_written_without_a_separator():
    education = [EducationEntry(degree="B.E", institution="Anna University", year="")]

    result = _widen_education_institutions(education, "B.E Anna University")

    assert result[0].institution == "Anna University"


def test_widen_only_matches_whole_words():
    education = [EducationEntry(degree="B.Sc", institution="Science College", year="")]

    result = _widen_education_institutions(education, "B.Sc, Life Science College, Pune")

    assert result[0].institution == "Life Science College"
    education = [EducationEntry(degree="B.Sc", institution="ege", year="")]
    assert _widen_education_institutions(education, "B.Sc, Life Science College")[0].institution == "ege"


# --- Entity text from the resume (_with_source_text) -------------------------


def test_entity_text_is_taken_from_the_resume_not_the_rebuilt_tokens():
    chunk = "Technical Lead/Operations Manager\nDell EMC"
    start = chunk.index("Technical")
    entity = {"entity_group": "Designation", "word": "Technical Lead / Operations Manager", "score": 0.9,
              "start": start, "end": start + len("Technical Lead/Operations Manager")}

    assert _with_source_text([entity], chunk)[0]["word"] == "Technical Lead/Operations Manager"


def test_a_span_across_a_line_break_becomes_one_line():
    chunk = "Wipro\nTechnologies Ltd"
    entity = {"entity_group": "Companies worked at", "word": "Wipro Technologies Ltd", "score": 0.9,
              "start": 0, "end": len(chunk)}

    assert _with_source_text([entity], chunk)[0]["word"] == "Wipro Technologies Ltd"


def test_entities_without_usable_offsets_keep_their_word():
    rows = [_entity("Designation", "Engineer"),                                   # start = end = 0
            {"entity_group": "Degree", "word": "B.Tech", "score": 0.9},           # no offsets at all
            {"entity_group": "Degree", "word": "MBA", "score": 0.9, "start": 3, "end": 99}]  # past the end

    assert [e["word"] for e in _with_source_text(rows, "short")] == ["Engineer", "B.Tech", "MBA"]


def test_parse_resume_local_reports_titles_as_written():
    text = "Experience\nTechnical Lead/Operations Manager\nDell EMC"

    def fake_pipeline(chunk):
        start = chunk.index("Technical")
        return [{"entity_group": "Designation", "word": "Technical Lead / Operations Manager", "score": 0.9,
                 "start": start, "end": start + len("Technical Lead/Operations Manager")}]

    profile = parse_resume_local(text, ner_pipeline=fake_pipeline)

    assert profile.experience[0].title == "Technical Lead/Operations Manager"


# --- Pairing degrees with the institution and year next to them (_align_education_to_lines) ---


def test_align_pairs_each_degree_with_the_institution_line_above_it():
    education = [
        EducationEntry(degree="Master of Computer Applications (MCA);", institution="Group of Institutions", year=""),
        EducationEntry(degree="Bachelor of Computer Applications (BCA)", institution="Nitte Meenakshi", year="2025"),
    ]
    text = (
        "Nitte Meenakshi Institute of Technology Bangalore, India\n"
        "Master of Computer Applications (MCA); SGPA: 7.69 2025 \u2013 2027\n"
        "Koshys Group of Institutions Bangalore, India\n"
        "Bachelor of Computer Applications (BCA); CGPA: 7.17 2024"
    )

    result = _align_education_to_lines(education, text)

    assert [(e.degree, e.institution, e.year) for e in result] == [
        ("Master of Computer Applications (MCA)", "Nitte Meenakshi Institute of Technology Bangalore", "2027"),
        ("Bachelor of Computer Applications (BCA)", "Koshys Group of Institutions Bangalore", "2024"),
    ]


def test_align_pairs_each_degree_with_the_institution_line_below_it():
    education = [
        EducationEntry(degree="M.Tech in CSE", institution="PSG College of Technology", year=""),
        EducationEntry(degree="B.Tech in IT", institution="", year=""),
    ]
    text = "M.Tech in CSE\nNIT Trichy 2020\nB.Tech in IT\nPSG College of Technology 2018"

    result = _align_education_to_lines(education, text)

    assert [(e.institution, e.year) for e in result] == [("NIT Trichy 2020", "2020"), ("PSG College of Technology 2018", "2018")]


def test_align_prefers_an_institution_on_the_degree_line():
    education = [EducationEntry(degree="B.Tech", institution="Wrong College", year="")]

    result = _align_education_to_lines(education, "B.Tech, Anna University, Chennai, 2019\nIIT Madras")

    assert (result[0].institution, result[0].year) == ("Anna University", "2019")


def test_align_leaves_an_entry_alone_when_no_institution_line_is_next_to_it():
    education = [EducationEntry(degree="B.Sc", institution="St. Xavier's College", year="2015")]

    result = _align_education_to_lines(education, "B.Sc\nGPA 3.8\nSt. Xavier's College")

    assert (result[0].institution, result[0].year) == ("St. Xavier's College", "2015")


def test_fill_education_institutions_knows_plural_keywords():
    education = [EducationEntry(degree="BCA", institution="", year="")]

    assert _fill_education_institutions(education, "BCA\nKoshys Group of Institutions")[0].institution == (
        "Koshys Group of Institutions"
    )
