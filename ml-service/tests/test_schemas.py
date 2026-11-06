"""The length caps on ResumeProfile (models/schemas.py): overlong values are
cut, not rejected, and stay under the backend's database column sizes."""

from app.models.schemas import ResumeProfile


def test_overlong_profile_fields_are_cut_to_their_caps():
    profile = ResumeProfile(
        name="n" * 500,
        email="e" * 400,
        phone="9" * 99,
        skills=["s" * 300] + [f"skill {i}" for i in range(400)],
        experience=[{"title": "t" * 999, "description": "d" * 9999}] * 50,
        education=[{"degree": "d" * 999}] * 50,
    )

    assert (len(profile.name), len(profile.email), len(profile.phone)) == (120, 254, 40)
    assert len(profile.skills) == 150 and len(profile.skills[0]) == 80
    assert len(profile.experience) == 30 and len(profile.experience[0].title) == 200
    assert len(profile.experience[0].description) == 2000
    assert len(profile.education) == 30 and len(profile.education[0].degree) == 200


def test_caps_also_apply_when_skills_are_replaced_later():
    profile = ResumeProfile()

    profile.skills = ["x" * 300] * 200

    assert len(profile.skills) == 150 and len(profile.skills[0]) == 80


def test_normal_values_are_left_alone():
    profile = ResumeProfile(name="Priya Sharma", phone="+91 98765 43210", skills=["Java"])

    assert (profile.name, profile.phone, profile.skills) == ("Priya Sharma", "+91 98765 43210", ["Java"])
