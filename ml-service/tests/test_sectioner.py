"""Tests sectioner.py's heading-based section splitting (FR-1.6). Pure
function over hand-built text -- no model, no I/O.
"""

from app.services.sectioner import split_sections


def test_resume_with_no_recognized_heading_falls_back_to_other():
    text = "Jane Doe\nSoftware Engineer\njane@example.com"

    sections = split_sections(text)

    assert sections.other == text
    assert sections.skills == ""
    assert sections.experience == ""
    assert sections.education == ""


def test_splits_lines_under_each_recognized_heading():
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

    sections = split_sections(text)

    assert sections.skills == "Python, SQL"
    assert sections.experience == "Backend Engineer at Acme Corp"
    assert sections.education == "B.Tech Computer Science, IIT Bombay"
    assert sections.other == "Jane Doe"


def test_heading_matching_is_case_insensitive_and_accepts_known_synonyms():
    text = "\n".join(["WORK EXPERIENCE", "Intern at Widgets Inc", "core competencies", "SQL"])

    sections = split_sections(text)

    assert sections.experience == "Intern at Widgets Inc"
    assert sections.skills == "SQL"


def test_lines_before_the_first_heading_go_to_other():
    text = "\n".join(["Jane Doe", "jane@example.com", "Education", "B.Sc Physics"])

    sections = split_sections(text)

    assert sections.other == "Jane Doe\njane@example.com"
    assert sections.education == "B.Sc Physics"


def test_a_heading_like_line_that_is_not_alone_on_its_line_is_not_treated_as_a_heading():
    text = "My skills include Python and SQL"

    sections = split_sections(text)

    assert sections.other == text
    assert sections.skills == ""


def test_a_projects_heading_ends_education():
    text = (
        "Education\nNitte Meenakshi Institute of Technology\nMCA 2027\n"
        "Projects\nMeme Arena | voting platform\n"
        "Hackathons & Open Source Contributions\nOpenKeyHub\n"
        "Technical Skills\nJava, SQL"
    )

    sections = split_sections(text)

    assert sections.education == "Nitte Meenakshi Institute of Technology\nMCA 2027"
    assert "Meme Arena" in sections.other and "OpenKeyHub" in sections.other
    assert sections.skills == "Java, SQL"


def test_internships_count_as_experience():
    sections = split_sections("Internships\nSoftware Intern, Acme\nEducation\nB.Tech")

    assert sections.experience == "Software Intern, Acme"
    assert sections.education == "B.Tech"


def test_only_unparsed_headings_still_fall_back_to_the_whole_text():
    text = "Projects\nMeme Arena\nCertifications\nAWS Cloud Foundations"

    sections = split_sections(text)

    assert sections.other == text
    assert sections.education == "" and sections.experience == ""


def test_a_long_line_starting_with_a_heading_word_is_content():
    text = "Education\nB.Tech\nProjects built during the degree include a compiler and a database engine"

    assert "compiler" in split_sections(text).education
