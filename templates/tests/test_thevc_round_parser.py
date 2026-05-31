"""Tests for TheVC round parser — rejects page chrome, accepts real labels."""
from ce_thevc import parse_round_from_text


class TestParseRoundFromText:
    def test_rejects_nav_tab_ma(self):
        body = "회사 개요 투자/M&A 뉴스 채용 인원 현황"
        assert parse_round_from_text(body) is None

    def test_rejects_standalone_ma(self):
        body = "이 회사는 M&A 시장에서 활발히 활동하고 있습니다."
        assert parse_round_from_text(body) is None

    def test_extracts_series_a_with_context(self):
        body = "현재 라운드 Series A 누적 투자금 50억원"
        assert parse_round_from_text(body) == "Series A"

    def test_extracts_series_b_with_context(self):
        body = "최근 투자 Series B+ 투자자 알토스벤처스"
        assert parse_round_from_text(body) == "Series B+"

    def test_extracts_seed_with_context(self):
        body = "라운드 Seed 투자금 10억원"
        assert parse_round_from_text(body) == "Seed"

    def test_extracts_pre_ipo(self):
        body = "투자 단계: Pre IPO 누적 300억원"
        assert parse_round_from_text(body) == "Pre IPO"

    def test_extracts_series_without_explicit_label(self):
        body = "에어스메디컬은 Series B 이후 성장 중"
        assert parse_round_from_text(body) == "Series B"

    def test_returns_none_for_empty_text(self):
        assert parse_round_from_text("") is None

    def test_returns_none_for_login_wall(self):
        body = "로그인이 필요합니다 Sign in to continue 투자/M&A"
        assert parse_round_from_text(body) is None

    def test_extracts_ipo_with_context(self):
        body = "현재 라운드 IPO 시가총액 1조원"
        assert parse_round_from_text(body) == "IPO"

    def test_extracts_real_ma_with_context(self):
        body = "현재 라운드 M&A 인수 완료"
        assert parse_round_from_text(body) == "M&A"
