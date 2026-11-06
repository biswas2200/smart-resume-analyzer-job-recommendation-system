"""domain_classifier.detect_domain(): deterministic, offline, and biased so
that an engineering resume can never leave the local path. The
embedding model is stubbed with a tiny bag-of-words vectoriser so the tests
need no model download and run in milliseconds.
"""

import zlib

import numpy as np
import pytest

from app.services import domain_classifier, embeddings

ENGINEERING_RESUME = """
Jane Doe -- Backend Software Engineer
Summary: 5 years building REST APIs and microservices.
Skills: Java, Spring Boot, Python, SQL, Docker, Kubernetes, Git
Experience
Backend Engineer, Acme Corp, 2019-2024
"""

NURSING_RESUME = """
Maria Lopez, RN
Registered Nurse with 6 years of acute care experience.
Skills: Nursing, Patient Care, Medication Administration, ACLS, BLS, Patient Education
Experience
Registered Nurse, City Hospital, 2018-2024
"""

ACCOUNTING_RESUME = """
Sam Patel, CPA
Senior Accountant experienced in financial reporting.
Skills: Accounting, Financial Reporting, GAAP, General Ledger, Journal Entries, Financial Statements
Experience
Staff Accountant, Ledger & Co, 2017-2024
"""


def _bag_of_words_embed(texts: list[str]) -> np.ndarray:
    """Deterministic stand-in for MiniLM: hashed bag-of-words, L2-normalised.
    crc32 rather than hash(): str hashing is salted per process, which made
    near-tie cases flip between runs."""
    vectors = np.zeros((len(texts), 64))
    for i, text in enumerate(texts):
        for word in text.lower().split():
            vectors[i, zlib.crc32(word.encode()) % 64] += 1.0
        norm = np.linalg.norm(vectors[i])
        if norm:
            vectors[i] /= norm
    return vectors


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings, "embed", _bag_of_words_embed)
    domain_classifier._description_vectors.cache_clear()
    # These tests are about the keyword rules; with this 64-bucket hash embedder a role title can
    # collide with a resume line by chance, so the role evidence is switched off here and tested
    # separately (test_role_evidence_*) with a controlled embedder.
    monkeypatch.setattr(domain_classifier, "_role_vectors", lambda: ({}, np.zeros((0, 64)), np.zeros((0, 64))))
    yield
    domain_classifier._description_vectors.cache_clear()


def test_engineering_resume_is_engineering_local():
    detection = domain_classifier.detect_domain(ENGINEERING_RESUME)

    assert detection.domain == "engineering"
    assert detection.engine == "local"
    assert 0.5 <= detection.confidence <= 1.0


def test_nursing_resume_is_healthcare_and_read_locally():
    detection = domain_classifier.detect_domain(NURSING_RESUME)

    assert detection.domain == "healthcare"
    assert detection.name == "Healthcare & Life Sciences"
    assert detection.engine == "local"


def test_accounting_resume_is_finance():
    assert domain_classifier.detect_domain(ACCOUNTING_RESUME).domain == "finance_accounting"


def test_three_engineering_skills_force_engineering_unless_another_domain_has_more_evidence():
    # Three engineering skills on an otherwise thin resume: engineering,
    # whatever the embedding says.
    thin = "Sam Roe\nSkills: Python, SQL, Docker\nOpen to opportunities."
    assert domain_classifier.detect_domain(thin).domain == "engineering"

    # The same three on a nursing resume do not outvote six healthcare
    # skills: a nurse who scripts reports is still a nurse.
    text = NURSING_RESUME + "\nAlso familiar with Python, SQL and Docker for reporting."
    assert domain_classifier.detect_domain(text).domain == "healthcare"

    text_two = NURSING_RESUME + "\nAlso familiar with Python and SQL."
    assert domain_classifier.detect_domain(text_two).domain == "healthcare"


def test_business_tools_in_the_engineering_taxonomy_do_not_capture_an_accountant():
    # Excel, Power BI and Budgeting are engineering-taxonomy skills too; a
    # finance resume that lists them stays finance.
    text = ACCOUNTING_RESUME + "\nTools: Excel, Power BI, Budgeting, Forecasting, Variance Analysis"
    assert domain_classifier.detect_domain(text).domain == "finance_accounting"


def test_detection_is_deterministic():
    first = domain_classifier.detect_domain(ACCOUNTING_RESUME)
    second = domain_classifier.detect_domain(ACCOUNTING_RESUME)

    assert first == second


def test_empty_text_still_returns_a_domain_with_zero_confidence():
    detection = domain_classifier.detect_domain("")

    assert detection.domain in domain_classifier.domain_by_id()
    assert detection.confidence == 0.0


def test_every_domain_has_an_engine_and_no_tier():
    for domain in domain_classifier.load_domains():
        assert domain["engine"] in {"local", "llm"}
        assert "tier" not in domain
    engineering = domain_classifier.domain_by_id()["engineering"]
    assert engineering["engine"] == "local"


# ---------------------------------------------------------------------------
# The ten AI-engine domains added 2026-09-14 -- above all, non-IT engineers must
# never land on the software pipeline (or in construction trades / design).
# ---------------------------------------------------------------------------

MECHANICAL_RESUME = """
Arjun Mehta -- Mechanical Engineer, 5 years in automotive component design.
Skills: SolidWorks, AutoCAD, GD&T, FEA, ANSYS, DFMEA, CATIA, Injection Moulding, Tolerance Analysis
Experience
Design Engineer, Tata Motors, 2019-2024
"""
CIVIL_RESUME = """
Priya Nair -- Civil Engineer (Structural), 6 years on highway and bridge projects.
Skills: STAAD Pro, AutoCAD Civil 3D, Structural Analysis, Reinforced Concrete Design, Site Supervision, Primavera P6
Experience
Site Engineer, L&T Construction, 2018-2024
"""
ELECTRICAL_RESUME = """
Rohan Das -- Electrical Engineer, power distribution and substation design.
Skills: ETAP, Power Systems, Switchgear, Protection Relays, PLC, SCADA, Transformer Sizing, Load Flow Analysis
Experience
Electrical Engineer, Siemens, 2017-2024
"""
PROCESS_RESUME = """
Neha Singh -- Process Engineer in a petrochemical refinery.
Skills: Chemical Engineering, Process Design, Aspen HYSYS, Process Simulation, P&ID, HAZOP, Distillation, Process Safety Management
Experience
Process Engineer, Reliance Industries, 2016-2024
"""


@pytest.mark.parametrize("resume", [MECHANICAL_RESUME, CIVIL_RESUME, ELECTRICAL_RESUME, PROCESS_RESUME])
def test_non_it_engineers_are_core_engineering_not_software(resume):
    detection = domain_classifier.detect_domain(resume)

    assert detection.domain == "core_engineering"
    assert detection.engine == "local"


@pytest.mark.parametrize("resume, expected", [
    ("Vikram Rao -- Quality Engineer.\nSkills: Root Cause Analysis, Six Sigma, ISO 9001, PPAP, SPC, Quality Inspection, Calipers\n"
     "Experience\nQuality Engineer, Bosch, 2018-2024", "quality_safety"),
    ("Kavya Menon -- PMP Project Manager.\nSkills: Project Management, Risk Management, Stakeholder Management, Budgeting, Scheduling, PMP\n"
     "Experience\nProgram Manager, Infosys BPM, 2016-2024", "consulting_project_management"),
    ("Deepak Kumar -- Store Manager.\nSkills: Retail Management, Merchandising, Inventory Management, Store Management, Loss Prevention\n"
     "Experience\nStore Manager, Reliance Retail, 2017-2024", "retail_ecommerce"),
    ("Anjali Das -- Licensed Social Worker.\nSkills: Case Management, Social Work, Crisis Intervention, Advocacy, Counseling, Treatment Planning\n"
     "Experience\nCase Manager, CRY, 2018-2024", "social_services"),
    ("Suresh Pillai -- Relationship Banker.\nSkills: Banking, Underwriting, Loan Origination, Risk Assessment, Retail Banking, NMLS\n"
     "Experience\nUniversal Banker, HDFC Bank, 2016-2024", "banking_insurance"),
    ("Dr. Meera Shah -- Small animal veterinarian.\nSkills: Veterinary Medicine, Surgery, Animal Care, Ultrasound, Dentistry\n"
     "Experience\nVeterinarian, Cessna Lifeline, 2019-2024", "veterinary_agriculture"),
    ("Ravi Yadav -- Production Supervisor.\nSkills: Production Supervision, Lean Manufacturing, Continuous Improvement, Production Planning, Machine Operation\n"
     "Experience\nProduction Supervisor, Bajaj Auto, 2015-2024", "manufacturing_production"),
    ("Nisha Verma -- Property Manager.\nSkills: Property Management, Leasing, Rent Collection, Yardi, Resident Relations, Vendor Management\n"
     "Experience\nAssistant Property Manager, Godrej Properties, 2018-2024", "real_estate_property"),
    ("Dr. Karan Bose -- Research Scientist.\nSkills: Molecular Biology, Biochemistry, Cell Culture, Flow Cytometry, HPLC, ELISA, Immunology\n"
     "Experience\nResearch Associate, NCBS, 2017-2024", "science_research"),
])
def test_each_new_domain_wins_its_own_resume(resume, expected):
    assert domain_classifier.detect_domain(resume).domain == expected


def test_the_catalogue_covers_every_llm_domain():
    from app.services import matcher

    for domain in domain_classifier.load_domains():
        if domain["engine"] == "llm":
            assert len(matcher._roles_in(domain["id"])) >= 8, domain["id"]


def test_role_evidence_separates_domains_the_description_alone_would_blur(monkeypatch):
    """A one-hot embedder: the headline equals one role title exactly, so the domain owning that
    role wins even though no keyword and no domain description points anywhere."""
    titles = ["Registered Nurse", "Staff Accountant", "Backend Developer"]
    vectors = {t: np.eye(len(titles))[i] for i, t in enumerate(titles)}

    def embed(texts):
        out = np.zeros((len(texts), len(titles)))
        for i, text in enumerate(texts):
            for t, vec in vectors.items():
                if t.lower() in text.lower():
                    out[i] += vec
        return out

    monkeypatch.setattr(embeddings, "embed", embed)
    domain_classifier._description_vectors.cache_clear()
    rows = {"healthcare": [0], "finance_accounting": [1], "engineering": [2]}
    matrix = embed(titles)
    monkeypatch.setattr(domain_classifier, "_role_vectors", lambda: (rows, matrix, matrix))

    detection = domain_classifier.detect_domain("Staff Accountant\nOpen to opportunities in the city.")

    assert detection.domain == "finance_accounting"


def test_the_headline_skips_the_candidate_name_and_contact_lines():
    text = "Maria Lopez\nmaria@example.com | +91 98765 43210\nRegistered Nurse\nSummary"

    assert domain_classifier._headline(text) == "Registered Nurse"


def test_the_headline_skips_generic_section_headings():
    text = "Professional Summary\nCareer Overview:\nAccomplishments\nSenior Registered Nurse\nWork History"

    assert domain_classifier._headline(text) == "Senior Registered Nurse"


def test_the_headline_skips_colleges_and_degrees():
    text = (
        "Maria Lopez\nmaria@example.com\nEducation:\nNitte Meenakshi Institute of Technology\n"
        "Master of Computer Applications (MCA)\nAug 2025 - Jul 2027\nWork History\nBackend Developer | Bosch | Jun 2024"
    )

    assert domain_classifier._headline(text).startswith("Backend Developer")


def test_the_opening_snippet_leaves_out_the_education_section():
    text = (
        "Maria Lopez\nRegistered Nurse\nEducation\nNitte Meenakshi Institute of Technology\n"
        "Master of Computer Applications\nExperience\nStaff Nurse, City Hospital, 2018-2024\nSkills\nNursing, ACLS"
    )

    snippet = domain_classifier._snippet(text)

    assert "Institute" not in snippet and "Master" not in snippet
    assert "Staff Nurse" in snippet and "ACLS" in snippet and "Registered Nurse" in snippet


def test_a_resume_without_an_education_heading_keeps_its_whole_opening():
    assert domain_classifier._snippet("Jane Roe\nBackend Developer\nSkills: Python") == "Jane Roe Backend Developer Skills: Python"


def test_a_single_stray_dictionary_hit_does_not_outvote_the_headline(monkeypatch):
    """One hit is a 100 % share for whichever domain lists it; it must not decide on its own."""
    monkeypatch.setattr(domain_classifier, "find_skills", lambda text, path=None: ["Counseling"] if path == domain_classifier.GENERAL_TAXONOMY_PATH else [])
    monkeypatch.setattr(domain_classifier, "_skill_to_domains", lambda: {"counseling": frozenset({"social_services"})})
    rows = {"engineering": [0], "social_services": [1]}
    matrix = np.array([[1.0, 0.0], [0.0, 1.0]])
    monkeypatch.setattr(domain_classifier, "_role_vectors", lambda: (rows, matrix, matrix))
    monkeypatch.setattr(embeddings, "embed", lambda texts: np.array([[1.0, 0.0]] * len(texts)))
    domain_classifier._description_vectors.cache_clear()

    detection = domain_classifier.detect_domain("Software Developer Intern\nCounseling")

    assert detection.domain == "engineering"
