"""Tests the skill-canonicalization lookup table in normalizer.py."""

from app.services.normalizer import normalize_skill, normalize_skills


def test_normalize_skill_maps_known_variant():
    assert normalize_skill("reactjs") == "React"
    assert normalize_skill("React.js") == "React"
    assert normalize_skill("  PYTHON3 ") == "Python"


def test_normalize_skill_passes_through_unknown():
    assert normalize_skill("Quantum Basket Weaving") == "Quantum Basket Weaving"


def test_normalize_skill_empty_string():
    assert normalize_skill("") == ""
    assert normalize_skill("   ") == ""


def test_normalize_skills_dedupes_and_preserves_order():
    result = normalize_skills(["React", "reactjs", "Python", "python3", "SQL"])
    assert result == ["React", "Python", "SQL"]
