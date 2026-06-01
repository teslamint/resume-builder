"""Characterization tests for resume_builder.py."""

import json

import resume_builder


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _configure_base(monkeypatch, tmp_path, config=None):
    base_config = config or {
        "job": {
            "companies": ["Acme"],
            "company_detail": {"Acme": "full"},
            "include_awards": True,
            "include_languages": True,
        },
        "public": {
            "companies": ["Acme"],
            "company_detail": {"Acme": "summary"},
            "include_awards": False,
            "include_languages": False,
        },
    }
    _write_json(tmp_path / "variant_config.json", base_config)
    monkeypatch.setattr(resume_builder, "BASE_DIR", tmp_path)
    monkeypatch.setattr(resume_builder, "_EXAMPLE_MODE", True)
    monkeypatch.setattr(resume_builder, "_GLOBAL_TARGET", None)
    return tmp_path


class TestCalculateTenure:
    def test_default_separator_includes_period_and_tenure(self):
        result = resume_builder.calculate_tenure("2020.09 - 2022.09")

        assert result == "2020.09 - 2022.09 (2년 1개월)"

    def test_tilde_separator_can_return_duration_only(self):
        result = resume_builder.calculate_tenure(
            "2020.09 ~ 2022.09",
            separator="~",
            include_period=False,
            error_value="",
        )

        assert result == "2년 1개월"


class TestLoadTargetConfig:
    def test_merges_target_overrides_into_base_variant_config(self, monkeypatch, tmp_path):
        _configure_base(monkeypatch, tmp_path)
        _write_json(
            tmp_path / "overrides" / "target-co" / "config.json",
            {
                "job": {
                    "companies": ["Beta"],
                    "company_detail": {"Acme": "summary", "Beta": "full"},
                    "include_awards": False,
                    "include_languages": False,
                }
            },
        )

        config = resume_builder.load_target_config("target-co", "job")

        assert config == {
            "companies": ["Beta"],
            "company_detail": {"Acme": "summary", "Beta": "full"},
            "include_awards": False,
            "include_languages": False,
        }

    def test_missing_or_invalid_target_config_keeps_base_config(self, monkeypatch, tmp_path):
        _configure_base(monkeypatch, tmp_path)
        _write(tmp_path / "overrides" / "broken" / "config.json", "{not-json")

        config = resume_builder.load_target_config("broken", "job")

        assert config["companies"] == ["Acme"]
        assert config["company_detail"] == {"Acme": "full"}
        assert config["include_awards"] is True
        assert config["include_languages"] is True


class TestBuildProfile:
    def test_build_profile_loads_enabled_sections_in_order(self, monkeypatch, tmp_path):
        _configure_base(
            monkeypatch,
            tmp_path,
            {
                "job": {
                    "companies": ["Acme"],
                    "company_detail": {"Acme": "full"},
                    "include_awards": False,
                    "include_languages": True,
                },
                "public": {"companies": []},
            },
        )
        _write(tmp_path / "profile" / "contact.md", "# Contact\n")
        _write(tmp_path / "profile" / "summary-job.md", "# Summary\n")
        _write(tmp_path / "profile" / "skills-job.md", "# Skills\n")
        _write(tmp_path / "profile" / "education.md", "# Education\n")
        _write(tmp_path / "profile" / "awards.md", "# Awards\n")
        _write(tmp_path / "profile" / "languages.md", "# Languages\n")

        parts = resume_builder.build_profile("job")

        assert parts == [
            "# Contact\n",
            "# Summary\n",
            "# Skills\n",
            "# Education\n",
            "# Languages\n",
        ]


class TestBuildCompany:
    def test_full_company_loads_profile_projects_and_achievements_with_variant_filtering(
        self, monkeypatch, tmp_path
    ):
        _configure_base(monkeypatch, tmp_path)
        company_dir = tmp_path / "companies" / "Acme"
        _write(
            company_dir / "profile.md",
            "# Acme\n\n"
            "## Overview\n\n"
            "- Period: 2021.01 - 2022.12\n"
            "- Role: Backend Engineer\n"
            "<!-- public-only:start -->\n"
            "public text\n"
            "<!-- public-only:end -->\n"
            "<!-- job-only:start -->\n"
            "job text\n"
            "<!-- job-only:end -->\n",
        )
        _write(
            company_dir / "projects" / "api.md",
            "## API Platform\n\n"
            "<!-- public-only:start -->\n"
            "public project\n"
            "<!-- public-only:end -->\n"
            "<!-- job-only:start -->\n"
            "job project\n"
            "<!-- job-only:end -->\n",
        )
        _write(company_dir / "achievements" / "impact.md", "## Impact\n\n- Reduced latency\n")
        _write(company_dir / "projects" / "CLAUDE.md", "ignored\n")

        parts = resume_builder.build_company(company_dir, "job")

        assert parts == [
            "# Acme\n\n## Overview\n\n- Period: 2021.01 - 2022.12\n- Role: Backend Engineer\njob text\n",
            "## API Platform\n\njob project\n",
            "## Impact\n\n- Reduced latency\n",
        ]

    def test_summary_company_loads_only_profile_overview(self, monkeypatch, tmp_path):
        _configure_base(
            monkeypatch,
            tmp_path,
            {
                "job": {
                    "companies": ["Acme"],
                    "company_detail": {"Acme": "summary"},
                    "include_awards": True,
                    "include_languages": True,
                },
                "public": {"companies": []},
            },
        )
        company_dir = tmp_path / "companies" / "Acme"
        _write(
            company_dir / "profile.md",
            "# Acme\n\n"
            "## Overview\n\n"
            "Overview line\n\n"
            "## Details\n\n"
            "Hidden details\n",
        )
        _write(company_dir / "projects" / "api.md", "## API Platform\n\nHidden project\n")

        parts = resume_builder.build_company(company_dir, "job")

        assert parts == ["# Acme\n\nOverview line"]


class TestBuildFull:
    def test_build_full_matches_known_profile_snapshot(self, monkeypatch, tmp_path):
        _configure_base(monkeypatch, tmp_path)
        _write(tmp_path / "profile" / "contact.md", "# Contact\n\n- Name: Test User\n")
        _write(tmp_path / "profile" / "summary-job.md", "# Summary\n\nBuilder summary\n")
        _write(tmp_path / "profile" / "skills-job.md", "# Skills\n\n- Python\n")
        _write(tmp_path / "profile" / "education.md", "# Education\n\n## Test University\n")
        _write(tmp_path / "profile" / "awards.md", "# Awards\n\n- Prize\n")
        _write(tmp_path / "profile" / "languages.md", "# Languages\n\n- Korean\n")
        company_dir = tmp_path / "companies" / "Acme"
        _write(
            company_dir / "profile.md",
            "# Acme\n\n## Overview\n\n- Period: 2021.01 - 2022.12\n- Role: Backend Engineer\n",
        )
        _write(company_dir / "projects" / "api.md", "## API Platform\n\nBuilt APIs\n")
        _write(company_dir / "achievements" / "impact.md", "## Impact\n\n- Reduced latency\n")

        result = resume_builder.build_full("job")

        assert result == (
            "# Contact\n\n- Name: Test User\n\n\n"
            "---\n\n"
            "# Summary\n\nBuilder summary\n\n\n"
            "---\n\n"
            "# Skills\n\n- Python\n\n\n"
            "---\n\n"
            "# Education\n\n## Test University\n\n\n"
            "---\n\n"
            "# Awards\n\n- Prize\n\n\n"
            "---\n\n"
            "# Languages\n\n- Korean\n\n\n"
            "---\n\n"
            "# Experience\n\n"
            "---\n\n"
            "# Acme\n\n## Overview\n\n- Period: 2021.01 - 2022.12\n- Role: Backend Engineer\n\n\n"
            "---\n\n"
            "## API Platform\n\nBuilt APIs\n\n\n"
            "---\n\n"
            "## Impact\n\n- Reduced latency\n"
        )
