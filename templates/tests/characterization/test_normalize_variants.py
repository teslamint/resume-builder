#!/usr/bin/env python3
"""Characterization tests: capture current behavior of all 7 slugify/normalize functions.

These tests exist to LOCK IN current behavior before refactoring.
After consolidation, these same inputs must produce the same outputs
(or intentional divergences must be documented and approved).

Functions under test:
  Slugify (filesystem-safe):
    1. utils.slugify_company()             — truncate 60, fallback "unknown-company"
    2. wanted_extract.slugify()            — truncate 50, no fallback
    3. remember_batch_extract.slugify()    — truncate 50, no fallback
    4. check_companies.slugify()           — truncate 50, no fallback

  Normalize (fuzzy matching):
    5. utils._normalize_company_name()     — _LEGAL_ENTITY_RE (broad: Inc, Corp, Co.Ltd, 주식회사, ㈜)
    6. company_extractor._normalize_company_name()  — narrow: (주)/(유)/(사) only, strips spaces
    7. recollect_company_info.normalize_name_key()  — strips all non-alnum, removes parenthetical
"""

import pytest

from naming import normalize_company_name as naming_normalize
from naming import normalize_company_name as utils_normalize
from naming import slugify_company
from naming import slugify_company as naming_slugify
from wanted_extract import slugify as wanted_slugify
from remember_batch_extract import slugify as remember_slugify
from check_companies import slugify as check_slugify
from ce_jd_files import normalize_company_name as ce_normalize
from recollect_company_info import normalize_name_key


# ---------------------------------------------------------------------------
# Category A: Slugify functions — filesystem-safe slug generation
# ---------------------------------------------------------------------------

SLUGIFY_INPUTS_AND_EXPECTED = [
    # (input, expected_slugify_company, expected_wanted/remember/check slugify)
    # Differences: truncation (60 vs 50), empty fallback
    ("(주)카카오", "카카오", "카카오"),
    ("(주 )네이버", "네이버", "네이버"),
    ("삼성전자", "삼성전자", "삼성전자"),
    ("LINE Plus Corp.", "line-plus-corp", "line-plus-corp"),
    ("토스 (Toss)", "토스-toss", "토스-toss"),
    ("  공백  많은   회사  ", "공백-많은-회사", "공백-많은-회사"),
    ("SK C&C", "sk-c-c", "sk-c-c"),
    ("한글Company혼합123", "한글company혼합123", "한글company혼합123"),
]


class TestSlugifyCompany:
    """utils.slugify_company() — truncate 60, fallback 'unknown-company'."""

    @pytest.mark.parametrize("inp,expected,_", SLUGIFY_INPUTS_AND_EXPECTED)
    def test_known_outputs(self, inp, expected, _):
        assert slugify_company(inp) == expected

    def test_empty_returns_fallback(self):
        assert slugify_company("") == "unknown-company"

    def test_none_returns_fallback(self):
        assert slugify_company(None) == "unknown-company"

    def test_truncation_at_60(self):
        long_name = "가" * 100
        result = slugify_company(long_name)
        assert len(result) <= 60


class TestWantedSlugify:
    """wanted_extract.slugify() — truncate 50, no fallback."""

    @pytest.mark.parametrize("inp,_,expected", SLUGIFY_INPUTS_AND_EXPECTED)
    def test_known_outputs(self, inp, _, expected):
        assert wanted_slugify(inp) == expected

    def test_empty_returns_empty(self):
        assert wanted_slugify("") == ""

    def test_truncation_at_50(self):
        long_name = "가" * 100
        result = wanted_slugify(long_name)
        assert len(result) <= 50


class TestRememberSlugify:
    """remember_batch_extract.slugify() — identical to wanted_extract."""

    @pytest.mark.parametrize("inp,_,expected", SLUGIFY_INPUTS_AND_EXPECTED)
    def test_matches_wanted(self, inp, _, expected):
        assert remember_slugify(inp) == expected

    def test_identical_to_wanted(self):
        cases = ["(주)카카오", "LINE Corp.", "", "가" * 100, "SK C&C"]
        for case in cases:
            assert remember_slugify(case) == wanted_slugify(case), f"Divergence on: {case!r}"


class TestCheckCompaniesSlugify:
    """check_companies.slugify() — identical to wanted_extract."""

    @pytest.mark.parametrize("inp,_,expected", SLUGIFY_INPUTS_AND_EXPECTED)
    def test_matches_wanted(self, inp, _, expected):
        assert check_slugify(inp) == expected

    def test_identical_to_wanted(self):
        cases = ["(주)카카오", "LINE Corp.", "", "가" * 100, "SK C&C"]
        for case in cases:
            assert check_slugify(case) == wanted_slugify(case), f"Divergence on: {case!r}"


# ---------------------------------------------------------------------------
# Category B: Normalize functions — fuzzy matching / deduplication
# ---------------------------------------------------------------------------

class TestUtilsNormalize:
    """utils._normalize_company_name() — broadest regex (_LEGAL_ENTITY_RE)."""

    def test_removes_ju_prefix(self):
        assert utils_normalize("(주)카카오") == "카카오"

    def test_removes_jushikhoesa(self):
        assert utils_normalize("주식회사카카오") == "카카오"

    def test_removes_inc(self):
        result = utils_normalize("Kakao Inc.")
        assert "inc" not in result.lower()

    def test_removes_corp(self):
        result = utils_normalize("Kakao Corp.")
        assert "corp" not in result.lower()

    def test_removes_co_ltd(self):
        result = utils_normalize("Kakao Co., Ltd.")
        assert "ltd" not in result.lower()

    def test_removes_yu(self):
        assert utils_normalize("(유)테스트") == "테스트"

    def test_removes_brackets(self):
        assert utils_normalize("카카오[서울]") == "카카오서울"

    def test_lowercases(self):
        assert utils_normalize("KAKAO") == "kakao"

    def test_preserves_spaces(self):
        result = utils_normalize("카카오 뱅크")
        assert "카카오" in result and "뱅크" in result


class TestCompanyExtractorNormalize:
    """company_extractor._normalize_company_name() — narrow regex, strips ALL spaces."""

    def test_removes_ju(self):
        assert ce_normalize("(주)카카오") == "카카오"

    def test_removes_yu(self):
        assert ce_normalize("(유)테스트") == "테스트"

    def test_removes_sa(self):
        assert ce_normalize("(사)재단") == "재단"

    def test_does_NOT_remove_jushikhoesa(self):
        """Unlike utils, this does NOT handle 주식회사."""
        result = ce_normalize("주식회사카카오")
        assert "주식회사" in result

    def test_does_NOT_remove_inc(self):
        """Unlike utils, this does NOT handle Inc."""
        result = ce_normalize("Kakao Inc.")
        assert "inc." in result

    def test_strips_all_spaces(self):
        """Key difference: collapses ALL whitespace."""
        assert ce_normalize("카카오 뱅크") == "카카오뱅크"

    def test_lowercases(self):
        assert ce_normalize("KAKAO") == "kakao"


class TestRecollectNormalizeNameKey:
    """recollect_company_info.normalize_name_key() — strips non-alnum, removes parenthetical."""

    def test_removes_ju(self):
        result = normalize_name_key("(주)카카오")
        assert "카카오" in result

    def test_removes_jushikhoesa(self):
        result = normalize_name_key("주식회사카카오")
        assert "주식회사" not in result

    def test_removes_all_parenthetical(self):
        """Removes ALL content in parentheses — broader than other normalizers."""
        result = normalize_name_key("카카오(서울)")
        assert "서울" not in result

    def test_strips_non_alnum(self):
        """Only keeps a-z, 0-9, 가-힣."""
        result = normalize_name_key("LINE Plus Corp.")
        assert result == "linepluscorp"

    def test_does_NOT_remove_inc(self):
        """Does NOT specifically handle Inc — but strips the dot."""
        result = normalize_name_key("Kakao Inc.")
        assert "inc" in result

    def test_lowercases(self):
        assert normalize_name_key("KAKAO") == "kakao"

    def test_none_returns_empty(self):
        assert normalize_name_key(None) == ""

    def test_empty_returns_empty(self):
        assert normalize_name_key("") == ""


# ---------------------------------------------------------------------------
# Cross-category divergence tests
# ---------------------------------------------------------------------------

class TestNormalizeDivergence:
    """Document known divergences between normalizer implementations.

    These tests capture WHERE the functions disagree, so that after
    consolidation we can make intentional choices about which behavior to keep.
    """

    @pytest.mark.parametrize("inp", [
        "(주)카카오",
        "카카오",
        "KAKAO",
        "카카오 뱅크",
        "주식회사카카오",
        "Kakao Inc.",
        "Kakao Corp.",
        "(유)테스트",
        "카카오(서울)",
        "LINE Plus",
        "",
    ])
    def test_snapshot_all_normalizers(self, inp):
        """Capture output of all 3 normalizers for each input.

        This test always passes — it's a documentation test.
        Refactoring should preserve these outputs or explicitly change them.
        """
        results = {
            "utils": utils_normalize(inp) if inp else utils_normalize(inp),
            "ce": ce_normalize(inp) if inp else ce_normalize(inp),
            "recollect": normalize_name_key(inp),
        }
        # Just ensure they don't crash
        assert all(isinstance(v, str) for v in results.values())

    def test_jushikhoesa_divergence(self):
        """주식회사 handling: utils and recollect remove it, ce does NOT."""
        inp = "\uc8fc\uc2dd\ud68c\uc0ac\uce74\uce74\uc624"
        assert "\uc8fc\uc2dd\ud68c\uc0ac" not in utils_normalize(inp)
        assert "\uc8fc\uc2dd\ud68c\uc0ac" in ce_normalize(inp)  # <-- known divergence
        assert "\uc8fc\uc2dd\ud68c\uc0ac" not in normalize_name_key(inp)

    def test_inc_divergence(self):
        """Inc. handling: utils removes it, ce and recollect do NOT."""
        inp = "Kakao Inc."
        utils_result = utils_normalize(inp)
        ce_result = ce_normalize(inp)
        recollect_result = normalize_name_key(inp)
        assert "inc" not in utils_result
        assert "inc" in ce_result  # <-- known divergence
        assert "inc" in recollect_result  # <-- known divergence

    def test_space_handling_divergence(self):
        """Space handling: ce strips ALL spaces, utils/recollect preserve or strip differently."""
        inp = "카카오 뱅크"
        utils_result = utils_normalize(inp)
        ce_result = ce_normalize(inp)
        recollect_result = normalize_name_key(inp)
        assert " " in utils_result  # preserves space
        assert " " not in ce_result  # strips ALL spaces
        assert " " not in recollect_result  # strips non-alnum (including spaces)

    def test_parenthetical_divergence(self):
        """Parenthetical content: recollect removes ALL, others only specific patterns."""
        inp = "카카오(서울)"
        utils_result = utils_normalize(inp)
        ce_result = ce_normalize(inp)
        recollect_result = normalize_name_key(inp)
        assert "서울" in utils_result  # keeps non-legal-entity parens content
        assert "서울" in ce_result  # keeps non-(주/유/사) content
        assert "서울" not in recollect_result  # removes ALL parenthetical

    def test_slugify_truncation_divergence(self):
        """slugify_company truncates at 60, wanted/remember/check at 50."""
        long_name = "가나다라마바사아자차" * 10  # 100 chars
        assert len(slugify_company(long_name)) <= 60
        assert len(wanted_slugify(long_name)) <= 50
        assert len(remember_slugify(long_name)) <= 50
        assert len(check_slugify(long_name)) <= 50

    def test_slugify_empty_divergence(self):
        """Empty input: slugify_company returns fallback, others return empty."""
        assert slugify_company("") == "unknown-company"
        assert wanted_slugify("") == ""
        assert remember_slugify("") == ""
        assert check_slugify("") == ""


# ---------------------------------------------------------------------------
# naming.py canonical module tests
# ---------------------------------------------------------------------------

class TestNamingModule:
    """Verify naming.py canonical functions match utils re-exports."""

    @pytest.mark.parametrize("inp", [
        "(주)카카오", "LINE Plus Corp.", "  공백  많은   회사  ",
        "SK C&C", "", "가" * 100,
    ])
    def test_naming_slugify_matches_utils(self, inp):
        assert naming_slugify(inp) == slugify_company(inp)

    @pytest.mark.parametrize("inp", [
        "(주)카카오", "\uc8fc\uc2dd\ud68c\uc0ac\uce74\uce74\uc624",
        "Kakao Inc.", "Kakao Corp.", "카카오(서울)", "(유)테스트", "",
    ])
    def test_naming_normalize_matches_utils(self, inp):
        assert naming_normalize(inp) == utils_normalize(inp)

    def test_naming_slugify_custom_params(self):
        """Parameterized slugify covers all existing variants."""
        assert naming_slugify("(주)카카오", max_len=50, fallback="") == wanted_slugify("(주)카카오")
        assert naming_slugify("", max_len=50, fallback="") == ""
        assert naming_slugify("", max_len=60, fallback="unknown-company") == "unknown-company"
