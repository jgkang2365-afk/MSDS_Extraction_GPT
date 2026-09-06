import pytest

from src.msds.models import ContentStatus, ResultStatus
from src.msds.normalization import CasValidity, is_valid_cas, normalize_cas, normalize_cas_result, normalize_content, normalize_product


@pytest.mark.parametrize("raw", ["64-17-5", "64−17−5", "64 – 17 – 5"])
def test_cas_normalization_is_limited_to_dashes_and_separator_whitespace(raw):
    result = normalize_cas(raw)
    assert result.normalized == "64-17-5"
    assert result.validity is CasValidity.VALID
    assert result.raw == raw


@pytest.mark.parametrize("raw", ["2024-01-1", "2024-01-12", "EC 205-399-7", "205-399-7"])
def test_dates_and_ec_numbers_are_not_promoted_to_cas(raw):
    assert not is_valid_cas(raw)


def test_check_digit_failure_is_reported_without_auto_correction():
    result = normalize_cas("64-17-4")
    assert result.normalized == "64-17-4"
    assert result.validity is CasValidity.CHECK_DIGIT_INVALID
    assert normalize_cas_result("64-17-4").cas_status is ResultStatus.INVALID


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10~20", "10~20"),
        ("10~20%", "10~20%"),
        ("< 1 %", "<1%"),
        ("> 10%", ">10%"),
        ("≤ 5 %", "≤5%"),
        ("≥80%", "≥80%"),
        ("0.1 ～ < 1 %", "0.1~<1%"),
        ("0.1~<1%", "0.1~<1%"),
        ("98.5 ∼ 101.5%", "98.5~101.5%"),
        ("0,1 ~ < 1,0 %", "0.1~<1.0%"),
        ("Rem.", "Rem."),
        ("Balance", "Balance"),
        ("  10 wt %  ", "10 wt%"),
        ("20 vol%", "20 vol%"),
    ],
)
def test_content_normalization_preserves_meaning_and_raw_value(raw, expected):
    result = normalize_content(raw)
    assert result.content_raw == raw
    assert result.content_normalized == expected
    assert result.content_status is ContentStatus.FOUND


def test_content_does_not_invent_percent_or_change_ambiguous_comma_grouping():
    assert normalize_content("Balance").normalized == "Balance"
    assert normalize_content("1,000%").normalized == "1,000%"
    assert normalize_content("").content_status is ContentStatus.NOT_STATED


def test_product_normalization_keeps_raw_model_grade_parentheses_concentration_and_symbols():
    raw = "  MICONOL C2M(H) Grade-A 10% #X1  "
    result = normalize_product(raw)
    assert result.raw == raw
    assert result.normalized == "miconol c2m(h) grade-a 10% #x1"
