"""Context builders: person dicts and household aggregation."""

from __future__ import annotations

from datetime import date

from app.eligibility.context import (
    PersonProfile,
    build_household_context,
    build_person_context,
)

ADULT_FEMALE = PersonProfile(
    name="Lakshmi",
    dob=date(1990, 3, 15),
    gender="female",
    annual_income=180000,
    state="Tamil Nadu",
    district="Coimbatore",
    pincode="641001",
    education="undergraduate",
    marital_status="married",
)


def test_person_context_derives_flags_from_dob() -> None:
    context = build_person_context(ADULT_FEMALE)
    assert context["age"] >= 30
    assert context["is_senior"] is False
    assert context["is_minor"] is False
    assert context["gender"] == "female"
    assert context["annual_income"] == 180000
    assert context["education_status"] == "undergraduate"
    assert context["is_widow"] is False  # marital status is married
    assert "is_student" not in context  # occupation not student


def test_missing_dob_leaves_age_fields_out() -> None:
    context = build_person_context(PersonProfile(name="X", gender="male"))
    assert "age" not in context
    assert "is_senior" not in context
    assert "is_minor" not in context


def test_senior_and_minor_flags() -> None:
    senior = build_person_context(
        PersonProfile(name="Old", dob=date(1945, 1, 1), gender="male")
    )
    assert senior["is_senior"] is True
    assert senior["is_minor"] is False

    minor = build_person_context(
        PersonProfile(name="Kid", dob=date(2015, 1, 1), gender="female")
    )
    assert minor["is_minor"] is True
    assert senior["is_senior"] is True


def test_widow_derived_from_marital_status() -> None:
    context = build_person_context(
        PersonProfile(name="W", dob=date(1970, 1, 1), marital_status="widowed")
    )
    assert context["is_widow"] is True


def test_explicit_is_widow_column_wins() -> None:
    context = build_person_context(
        PersonProfile(name="W", dob=date(1970, 1, 1), is_widow=True)
    )
    assert context["is_widow"] is True


def test_student_via_occupation() -> None:
    context = build_person_context(
        PersonProfile(name="S", dob=date(2006, 1, 1), occupation="student")
    )
    assert context["is_student"] is True


def test_explicit_is_student_column_wins() -> None:
    context = build_person_context(
        PersonProfile(name="S", dob=date(1990, 1, 1), is_student=False, occupation="student")
    )
    assert context["is_student"] is False


# --------------------------------------------------------------- household


def test_household_income_only_known_when_completely_known() -> None:
    context = build_household_context(ADULT_FEMALE, [PersonProfile(name="Child")])
    assert "household_income" not in context  # member income unknown
    assert context["family_size"] == 2

    context = build_household_context(
        ADULT_FEMALE,
        [PersonProfile(name="Child", dob=date(2015, 5, 5), annual_income=0)],
    )
    assert context["household_income"] == 180000
    assert context["family_size"] == 2


def test_household_senior_flag_is_three_valued() -> None:
    context = build_household_context(ADULT_FEMALE, [PersonProfile(name="Kid")])
    assert context["has_senior"] is None  # member age unknown

    context = build_household_context(
        ADULT_FEMALE, [PersonProfile(name="Kid", dob=date(2015, 5, 5))]
    )
    assert context["has_senior"] is False


def test_household_senior_flag_true_for_senior_member() -> None:
    context = build_household_context(
        ADULT_FEMALE, [PersonProfile(name="Mom", dob=date(1950, 1, 1), gender="female")]
    )
    assert context["has_senior"] is True


def test_girl_child_detection() -> None:
    context = build_household_context(
        ADULT_FEMALE,
        [
            PersonProfile(
                name="Daughter", dob=date(2014, 2, 2), gender="female", relationship="daughter"
            )
        ],
    )
    assert context["has_girl_child"] is True


def test_girl_child_unknown_without_dob() -> None:
    context = build_household_context(
        ADULT_FEMALE,
        [PersonProfile(name="Daughter", gender="female", relationship="daughter")],
    )
    assert context["has_girl_child"] is None


def test_boy_child_is_not_girl_child() -> None:
    context = build_household_context(
        ADULT_FEMALE, [PersonProfile(name="Son", dob=date(2014, 2, 2), gender="male")]
    )
    assert context["has_girl_child"] is False


def test_disabled_member_unknown_when_flag_unset() -> None:
    # Head's own disability unset: aggregate stays unknown even when a member
    # answered "no" — we still do not know about every household member.
    context = build_household_context(ADULT_FEMALE, [])
    assert context["has_disabled_member"] is None

    context = build_household_context(
        ADULT_FEMALE,
        [PersonProfile(name="Son", dob=date(2010, 1, 1), is_disabled=False)],
    )
    assert context["has_disabled_member"] is None

    # Everything (head included) known and no disability → definite False.
    head_known = PersonProfile(
        name="Lakshmi",
        dob=date(1990, 3, 15),
        is_disabled=False,
        annual_income=180000,
    )
    context = build_household_context(
        head_known,
        [PersonProfile(name="Son", dob=date(2010, 1, 1), is_disabled=False)],
    )
    assert context["has_disabled_member"] is False


def test_disabled_member_true() -> None:
    context = build_household_context(
        ADULT_FEMALE, [PersonProfile(name="Son", dob=date(2010, 1, 1), is_disabled=True)]
    )
    assert context["has_disabled_member"] is True


def test_has_student_over_members() -> None:
    context = build_household_context(
        ADULT_FEMALE, [PersonProfile(name="Son", dob=date(2010, 1, 1), is_student=True)]
    )
    assert context["has_student"] is True


def test_head_address_is_included() -> None:
    context = build_household_context(ADULT_FEMALE, [])
    assert context["state"] == "Tamil Nadu"
    assert context["district"] == "Coimbatore"
    assert context["pincode"] == "641001"

