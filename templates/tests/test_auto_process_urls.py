"""Focused characterization tests for auto._process_urls state behavior."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class TestProcessUrlsCharacterization:
    def test_full_pipeline_persists_state_round_trip(self, tmp_path):
        from auto_processor import _process_urls
        from auto_state import RunSummary, _load_state
        from auto_company import CompanyInfoResult

        run_id = "process-urls-state-round-trip"
        job_id = "123456"
        url = f"https://www.wanted.co.kr/wd/{job_id}"
        jd_path = tmp_path / f"{job_id}-stateco-backend.md"
        jd_path.write_text("# Backend\n", encoding="utf-8")
        classified_path = tmp_path / "pass" / jd_path.name
        company_file = tmp_path / "company_info" / "stateco.md"
        company_file.parent.mkdir()
        company_file.write_text("# StateCo\n", encoding="utf-8")
        screening_path = tmp_path / "screening.md"

        extracted = SimpleNamespace(
            output_path=jd_path,
            company="StateCo",
            title="Backend",
        )
        company_info = CompanyInfoResult(
            company="StateCo",
            file_path=company_file,
            used_existing=True,
            completeness=100.0,
            thevc_attempted=False,
            thevc_status="skipped",
            investment_data_source="existing",
        )
        screening = SimpleNamespace(
            screening_path=screening_path,
            verdict="지원 추천",
            used_fallback=False,
        )
        summary = RunSummary(run_id=run_id)

        with patch("auto_state.STATE_DIR", tmp_path / "state"), \
             patch("auto_processor.find_existing_jd", side_effect=[None, classified_path]), \
             patch("auto_processor.extract_jd_from_url", return_value=extracted) as mock_extract, \
             patch("auto_processor.ensure_company_info", return_value=company_info) as mock_company, \
             patch("auto_processor.run_screening", return_value=screening) as mock_screening, \
             patch("auto_processor._classify", return_value=("지원 추천", "pass")) as mock_classify, \
             patch("auto_processor._cleanup_state") as mock_cleanup:
            results, updated = _process_urls(
                urls=[url],
                run_id=run_id,
                config={"notifications": {}},
                summary=summary,
                state_items={},
                dry_run=False,
                screening_only=False,
                continue_on_error=True,
                llm_timeout=30,
                no_classify=False,
                thevc_mode="skip",
                min_completeness=70.0,
                allow_incomplete_company_info=False,
                resume=False,
                no_prescreen=True,
            )
            loaded_state = _load_state(run_id)

        mock_extract.assert_called_once_with(url)
        mock_company.assert_called_once_with(
            jd_path=jd_path,
            jd_url=url,
            company_name="StateCo",
            thevc_mode="skip",
            dry_run=False,
            min_completeness=70.0,
        )
        mock_screening.assert_called_once_with(
            jd_path=jd_path,
            company_file=Path(company_file),
            llm_timeout=30,
            dry_run=False,
        )
        mock_classify.assert_called_once_with(jd_path, dry_run=False)
        mock_cleanup.assert_called_once_with(run_id)

        assert updated.processed == 1
        assert updated.extracted == 1
        assert updated.screened == 1
        assert updated.recommended == 1
        assert results[0].status == "processed"
        assert results[0].jd_path == str(classified_path)
        assert results[0].company_file == str(company_file)
        assert loaded_state[job_id]["stage"] == "done"
        assert loaded_state[job_id]["status"] == "done"
        assert loaded_state[job_id]["jd_path"] == str(classified_path)
        assert loaded_state[job_id]["screening_path"] == str(screening_path)
        assert loaded_state[job_id]["verdict"] == "지원 추천"
