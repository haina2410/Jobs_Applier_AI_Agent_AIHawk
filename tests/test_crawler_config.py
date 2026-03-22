import tempfile
from pathlib import Path
import pytest
import yaml
from src.crawlers.config import CrawlerConfig


def _write_yaml(data: dict, path: Path):
    path.write_text(yaml.dump(data))


def test_load_valid_config(tmp_path):
    cfg_path = tmp_path / "crawler_config.yaml"
    _write_yaml({
        "enabled_crawlers": ["linkedin"],
        "linkedin": {
            "filters": {
                "keywords": "Engineer",
                "location": "NYC",
                "experience_level": ["entry"],
                "job_type": ["full-time"],
                "work_type": ["remote"],
                "date_posted": "past_week",
            },
            "max_jobs_per_run": 10,
            "max_pages": 2,
        },
        "rate_limiting": {"min_delay": 1, "max_delay": 3},
        "output": {"generate_resume": True, "generate_cover_letter": False, "style": "Classic"},
    }, cfg_path)
    config = CrawlerConfig.load(cfg_path)
    assert config.enabled_crawlers == ["linkedin"]
    assert config.linkedin["filters"]["keywords"] == "Engineer"
    assert config.rate_limiting["min_delay"] == 1
    assert config.output["style"] == "Classic"


def test_missing_enabled_crawlers_raises(tmp_path):
    cfg_path = tmp_path / "crawler_config.yaml"
    _write_yaml({"linkedin": {}}, cfg_path)
    with pytest.raises(ValueError, match="enabled_crawlers"):
        CrawlerConfig.load(cfg_path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        CrawlerConfig.load(tmp_path / "nonexistent.yaml")


def test_experience_level_mapping():
    assert CrawlerConfig.EXPERIENCE_LEVEL_MAP["mid-senior"] == 4
    assert CrawlerConfig.EXPERIENCE_LEVEL_MAP["internship"] == 1
    assert CrawlerConfig.EXPERIENCE_LEVEL_MAP["executive"] == 6


def test_date_posted_mapping():
    assert CrawlerConfig.DATE_POSTED_MAP["past_24h"] == "r86400"
    assert CrawlerConfig.DATE_POSTED_MAP["past_week"] == "r604800"
    assert CrawlerConfig.DATE_POSTED_MAP["past_month"] == "r2592000"
