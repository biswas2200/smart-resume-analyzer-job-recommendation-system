"""Resume layouts the entity-order assembly got wrong. Each test feeds
parse_resume_local the entities the real model produced on that layout (found
by running the teacher model on it), so the assertions pin the repair passes
that read the resume's own lines: education blocks, cut-off spans, jobs the
model skipped, names, headings."""

from app.services.local_ner_parser import parse_resume_local
from app.services.sectioner import split_sections


def fake_ner(*tagged):
    """A pipeline that tags the given (label, text) pairs in order, with the
    character offsets the real pipeline reports."""

    def run(chunk):
        found, cursor = [], 0
        for label, text in tagged:
            start = chunk.find(text, cursor)
            if start == -1:
                continue
            cursor = start + len(text)
            found.append({"entity_group": label, "word": text, "score": 0.9, "start": start, "end": cursor})
        return found

    return run


KNOWN_ISSUE_RESUME = """Amitosh Kumar Biswas
amitosh@example.com

Education:
Nitte Meenakshi Institute of Technology
Master of Computer Applications (MCA)   CPI: 8.4
Aug 2025 - Jul 2027
Koshys Group of Institutions
Bachelor of Computer Applications (BCA)   CPI: 7.9
Aug 2022 - Jun 2025
"""


def test_institution_first_degrees_keep_their_own_institution_grade_and_year():
    # The model glued "CPI" onto each degree, tagged a bare month as the year,
    # and its entity order pairs each institution with the wrong degree.
    ner = fake_ner(
        ("College Name", "Nitte Meenakshi Institute of Technology"),
        ("Degree", "Master of Computer Applications (MCA)   CPI"),
        ("Graduation Year", "Jul"),
        ("College Name", "Koshys Group of Institutions"),
        ("Degree", "Bachelor of Computer Applications (BCA)   CPI"),
        ("Graduation Year", "Jun"),
    )

    education = parse_resume_local(KNOWN_ISSUE_RESUME, ner_pipeline=ner).education

    assert [(e.degree, e.institution, e.year) for e in education] == [
        ("Master of Computer Applications (MCA)", "Nitte Meenakshi Institute of Technology", "2027"),
        ("Bachelor of Computer Applications (BCA)", "Koshys Group of Institutions", "2025"),
    ]


def test_a_degree_the_model_never_tagged_is_still_found_from_its_line():
    text = "Education\nB.E. in Computer Science, Anna University, Chennai, 2020\nM.Tech in AI - IIT Madras - 2022\n"
    ner = fake_ner(("Degree", "B.E. in Computer Science"), ("College Name", "Anna University"))

    education = parse_resume_local(text, ner_pipeline=ner).education

    assert [(e.degree, e.institution, e.year) for e in education] == [
        ("B.E. in Computer Science", "Anna University", "2020"),
        ("M.Tech in AI", "IIT Madras", "2022"),
    ]


def test_a_cut_off_bracket_in_a_degree_is_closed():
    text = "Education\nBachelor of Computer Applications (BCA)\nKoshys Group of Institutions, 2025\n"
    ner = fake_ner(("Degree", "Bachelor of Computer Applications (BCA"), ("College Name", "Koshys Group of Institutions"))

    education = parse_resume_local(text, ner_pipeline=ner).education

    assert education[0].degree == "Bachelor of Computer Applications (BCA)"


JOBS_RESUME = """Rahul Sharma
Experience
Software Engineer, Infosys Limited, Bengaluru
Jun 2021 - Present
- Built REST APIs

Software Engineering Intern, Flipkart
Jan 2021 - May 2021
- Worked on recommendations
"""


def test_a_job_whose_title_the_model_missed_does_not_overwrite_the_previous_company():
    ner = fake_ner(
        ("Designation", "Software Engineer"),
        ("Companies worked at", "Infosys Limited"),
        ("Companies worked at", "Flipkart"),
    )

    jobs = parse_resume_local(JOBS_RESUME, ner_pipeline=ner).experience

    assert [(j.title, j.organization, j.duration) for j in jobs] == [
        ("Software Engineer", "Infosys Limited", "Jun 2021 - Present"),
        ("Software Engineering Intern", "Flipkart", "Jan 2021 - May 2021"),
    ]


def test_a_title_cut_short_by_the_model_is_completed_from_its_line():
    text = "Jane Doe\nExperience\nMachine Learning Engineer\nTCS Research Pune\n2023-2024\n"
    ner = fake_ner(("Designation", "Machine Learning"), ("Companies worked at", "TCS Research"))

    job = parse_resume_local(text, ner_pipeline=ner).experience[0]

    assert (job.title, job.organization) == ("Machine Learning Engineer", "TCS Research")


def test_a_company_the_model_cut_short_is_completed_but_a_city_is_not_added():
    text = "Jane Doe\nExperience\nAssociate Data Scientist\nMu Sigma Business Solutions\nJan 2022 - Present\n"
    ner = fake_ner(("Designation", "Associate Data Scientist"), ("Companies worked at", "Solutions"))

    assert parse_resume_local(text, ner_pipeline=ner).experience[0].organization == "Mu Sigma Business Solutions"


def test_a_job_date_on_its_own_line_wins_over_a_nearer_date_of_another_section():
    text = KNOWN_ISSUE_RESUME + "\nWork History\nSoftware Developer Intern | Bosch | Jun 2024 - Dec 2024\n"
    ner = fake_ner(("Designation", "Software Developer Intern"), ("Companies worked at", "Bosch"))

    assert parse_resume_local(text, ner_pipeline=ner).experience[0].duration == "Jun 2024 - Dec 2024"


def test_names_with_particles_suffixes_initials_and_contact_details_are_found():
    for first_line, expected in [
        ("Ludwig van der Meer Jr", "Ludwig van der Meer Jr"),
        ("AMITOSH KUMAR BISWAS | amitosh@example.com | +91 98765 43210", "AMITOSH KUMAR BISWAS"),
        ("A. K. Biswas", "A. K. Biswas"),
        ("Mary Anne Elizabeth Thompson", "Mary Anne Elizabeth Thompson"),
    ]:
        assert parse_resume_local(first_line + "\nExperience\n", ner_pipeline=lambda c: []).name == expected


def test_common_heading_variants_open_their_sections():
    text = "EDUCATION & QUALIFICATIONS\nB.Tech\n--- PROFESSIONAL EXPERIENCE ---\nEngineer at Acme\nKey Skills\nPython"

    sections = split_sections(text)

    assert "B.Tech" in sections.education
    assert "Engineer at Acme" in sections.experience
    assert "Python" in sections.skills


AMRUTHA_RESUME = """Amrutha
mailto:amruthaamrutha693@gmail.com • +91 7483727966
EDUCATION
Master of Computer Applications
NITTE Meenakshi Institute of Technology, Bengaluru, Karnataka-2025-(Present)
GPA: 9.04/10
Bachelor of Computer Applications
MES MSPS First Grade College, Chikkamangluru, Karnataka
GPA: 9.22/10
PCMB, Intermediate
Junior PU Govt College, Chikkamangluru, Karnataka
PROFESSIONAL EXPERIENCE
Data Science Trainee – Pragati: Path to Future (Cohort 9) – Infosys Springboard - Jul 2026-Present
- Currently undergoing training in Python, Data Science, Artificial Intelligence, and Machine Learning.
SKILLS
Programming Languages: Python, Java, SQL
Cybersecurity: Cybersecurity Fundamentals, SOC, Authentication & Authorization
Artificial Intelligence (AI): Generative AI, Prompt Engineering, Data Science
"""


def amrutha_profile():
    # What the teacher model returned on this PDF: no title for the job, part of
    # the college name tagged as a degree, a generic word tagged as a skill.
    ner = fake_ner(
        ("Companies worked at", "Infosys Springboard"),
        ("Skills", "Data"),
        ("Degree", "Master of Computer Applications"),
        ("College Name", "NITTE"),
        ("College Name", "Meenakshi Institute of Technology"),
        ("Graduation Year", "2025"),
        ("Degree", "Bachelor of Computer Applications"),
        ("Degree", "MES MSPS"),
        ("College Name", "First Grade College"),
        ("College Name", "Govt College"),
    )
    return parse_resume_local(AMRUTHA_RESUME, ner_pipeline=ner)


def test_a_one_word_name_followed_by_contact_details_is_the_name():
    assert amrutha_profile().name == "Amrutha"
    assert parse_resume_local("Education\nB.Tech\n", ner_pipeline=lambda c: []).name == ""
    assert parse_resume_local("Resume\nme@x.com\n", ner_pipeline=lambda c: []).name == ""


def test_part_of_a_college_name_tagged_as_a_degree_is_not_a_degree():
    education = amrutha_profile().education

    assert [(e.degree, e.institution) for e in education] == [
        ("Master of Computer Applications", "NITTE Meenakshi Institute of Technology"),
        ("Bachelor of Computer Applications", "MES MSPS First Grade College"),
        ("Intermediate", "Junior PU Govt College"),
    ]
    assert education[0].year == "2025" and education[1].year == ""


def test_a_company_the_model_found_without_a_title_gets_its_title_from_the_line():
    jobs = amrutha_profile().experience

    assert [(j.title, j.organization, j.duration) for j in jobs] == [
        ("Data Science Trainee", "Infosys Springboard", "Jul 2026-Present")
    ]


def test_skills_listed_in_the_skills_section_are_kept_and_generic_words_are_not():
    skills = amrutha_profile().skills

    for wanted in ("SOC", "Cybersecurity", "Generative AI", "Prompt Engineering", "Data Science"):
        assert wanted in skills
    assert "Data" not in skills


DIVYANSHI_RESUME = """Divyanshi Pathak
Email: divyanshipathak17@gmail.com
Education
Nitte Meenakshi Institute of Technology Bengaluru, India
•
Master of Computer Applications; CPI: 9.35 2025 – Present
ISBR Business School, Bangalore University Bengaluru, India
•
Bachelor of Computer Applications; CPI: 8.9 2022 – 2025
Skills Summary
• Programming Languages: Python, C/C++, SQL
Experience
Deradh Remote
•
Software Developer Intern Aug 2024 – Jan 2025
– Built scalable REST APIs.
Projects
UPI Fraud Detection System
"""


def divyanshi_profile():
    # The model tagged the company line "Deradh Remote" as a Name, so there is
    # no company entity at all.
    ner = fake_ner(
        ("Name", "Deradh Remote"),
        ("Designation", "Software Developer Intern"),
        ("College Name", "Nitte Meenakshi Institute of Technology"),
        ("Degree", "Master of Computer Applications; CPI"),
        ("College Name", "ISBR Business School, Bangalore University"),
        ("Degree", "Bachelor of Computer Applications; CPI"),
        ("Graduation Year", "2025"),
    )
    return parse_resume_local(DIVYANSHI_RESUME, ner_pipeline=ner)


def test_a_company_written_above_the_title_with_a_work_mode_word_is_found():
    job = divyanshi_profile().experience[0]

    assert (job.title, job.organization, job.duration) == ("Software Developer Intern", "Deradh", "Aug 2024 – Jan 2025")


def test_a_city_written_after_an_institution_is_not_part_of_its_name():
    education = divyanshi_profile().education

    assert education[0].institution == "Nitte Meenakshi Institute of Technology"
    assert education[0].degree == "Master of Computer Applications"
    assert education[1].institution == "ISBR Business School"
    # A name that merely ends in a place is left alone.
    from app.services.local_ner_parser import _trim_trailing_place
    assert _trim_trailing_place("University of Texas at Austin", []) == "University of Texas at Austin"
    assert _trim_trailing_place("Anna University Chennai", []) == "Anna University"


def test_a_bracket_listing_several_skills_gives_each_of_them_and_no_broken_item():
    from app.services.local_ner_parser import _skills_from_section

    skills = _skills_from_section(
        "Cloud & AI: Google Cloud (Firebase, Gemini API, IAM), Spring AI Core Abstraction\n"
        "Others: Data Structures & Algorithms (DSA), Agile"
    )

    assert skills == ["Google Cloud", "Firebase", "Gemini API", "IAM", "Spring AI Core Abstraction",
                      "Data Structures & Algorithms", "Agile"]
    assert not any(")" in item or "(" in item for item in skills)


def test_a_wrapped_skill_is_one_item_and_prose_and_headings_are_not_skills():
    from app.services.local_ner_parser import _skills_from_section

    skills = _skills_from_section(
        "Excel, Word, PowerPoint, Outlook, Access, Employee Relations, Alternative Dispute\nResolution (ADR), Performance Management.\n"
        "important to sales process, but not limited to, Mentored numerous new team members, etc, Additional Information"
    )

    assert skills == ["Excel", "Word", "PowerPoint", "Outlook", "Access", "Employee Relations",
                      "Alternative Dispute Resolution", "Performance Management"]


def test_placeholder_companies_and_junk_titles_are_cleaned_from_experience():
    from app.models.schemas import ExperienceEntry
    from app.services.local_ner_parser import _clean_experience

    jobs = _clean_experience([
        ExperienceEntry(title="HR Assistant", organization="HR Representative Company Name City"),
        ExperienceEntry(title="Executive Chef", organization="Current Company Name City", duration="2008 - Current"),
        ExperienceEntry(title="Accounting Clerk", organization="Clerk"),
        ExperienceEntry(title="Accountant", organization="State"),
        ExperienceEntry(title="A", organization="Acme"),
        ExperienceEntry(title="/", organization="Acme"),
        ExperienceEntry(title="General", organization=""),
        ExperienceEntry(title="Food Services Director/", organization="Acme Foods"),
    ])

    assert [(j.title, j.organization) for j in jobs] == [
        ("HR Assistant", "HR Representative"),
        ("Executive Chef", ""),
        ("Accounting Clerk", ""),
        ("Accountant", ""),
        ("Food Services Director", "Acme Foods"),
    ]


def test_a_job_title_on_the_first_line_is_not_taken_for_a_name():
    for first_line in ("HR GENERALIST", "PROFESSIONAL HEALTHCARE REPRESENTATIVE", "Executive Chef", "SENIOR ACCOUNTANT"):
        text = first_line + "\nSummary\nTen years of experience.\nExperience\n"
        assert parse_resume_local(text, ner_pipeline=lambda c: []).name == "", first_line


def test_mojibake_from_a_pdf_is_repaired_before_parsing():
    from app.services.local_ner_parser import fix_mojibake

    assert fix_mojibake("documentedÂ success inÂ driving") == "documented success in driving"
    assert fix_mojibake("Mississippi College ï¼​ City") == "Mississippi College  -  City"
    assert fix_mojibake("2012 â€“ 2014") == "2012 – 2014"
    assert fix_mojibake("plain text") == "plain text"


def test_a_degree_does_not_keep_the_college_the_model_tagged_with_it_and_a_leading_date_is_dropped():
    text = (
        "Education\n"
        "M.Com (Master of Commerce) University of Kerala, India\n"
        "Bachelor of Science : Nursing - May 2000 Mississippi College - City\n"
    )
    ner = fake_ner(("Degree", "M.Com (Master of Commerce) University of Kerala"), ("Degree", "Bachelor of Science : Nursing"))

    education = parse_resume_local(text, ner_pipeline=ner).education

    assert [(e.degree, e.institution) for e in education] == [
        ("M.Com (Master of Commerce)", "University of Kerala"),
        ("Bachelor of Science : Nursing", "Mississippi College"),
    ]
