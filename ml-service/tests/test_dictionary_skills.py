"""Tests dictionary_skills.py's whole-text taxonomy matching (FR-1.7).
Exercises the real skill_taxonomy.json (no model, no I/O beyond that static
file), so these assert against skills actually present there.
"""

from app.services.dictionary_skills import find_skills


def test_finds_a_single_token_skill_mentioned_in_prose():
    text = "I built several services in Python over the last two years."

    skills = find_skills(text)

    assert "Python" in skills


def test_finds_a_multi_token_skill_as_one_match():
    text = "Experience with REST APIs and SQL."

    skills = find_skills(text)

    assert "REST APIs" in skills
    assert "SQL" in skills


def test_does_not_false_positive_java_inside_javascript():
    text = "Built a frontend with JavaScript and no backend Java experience."

    skills = find_skills(text)

    assert "JavaScript" in skills
    # Java *is* separately mentioned in this text ("backend Java experience"),
    # so this only proves the JavaScript token wasn't double-counted as Java --
    # see the dedicated no-mention case below for the real substring-safety check.
    assert "Java" in skills


def test_java_is_not_matched_when_only_javascript_is_mentioned():
    text = "Frontend built entirely with JavaScript."

    skills = find_skills(text)

    assert "JavaScript" in skills
    assert "Java" not in skills


def test_returns_canonical_names_not_raw_variants():
    text = "reactjs and node.js developer"

    skills = find_skills(text)

    assert "React" in skills
    assert "Node.js" in skills


def test_no_taxonomy_mention_returns_empty_list():
    text = "A resume with no recognizable technology at all."

    skills = find_skills(text)

    assert skills == []


def test_each_skill_is_returned_only_once_even_if_mentioned_repeatedly():
    text = "Python, Python, and more Python."

    skills = find_skills(text)

    assert skills.count("Python") == 1
