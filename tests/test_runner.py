import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import yaml
import pytest


def _setup_data_folder(tmp_path):
    """Create a minimal data_folder for testing."""
    (tmp_path / "secrets.yaml").write_text(yaml.dump({
        "llm_api_key": "test-key",
        "linkedin_cookies": {"li_at": "test-cookie"},
    }))
    (tmp_path / "crawler_config.yaml").write_text(yaml.dump({
        "enabled_crawlers": ["linkedin"],
        "linkedin": {
            "filters": {"keywords": "Engineer", "location": "NYC"},
            "max_jobs_per_run": 2,
            "max_pages": 1,
        },
        "rate_limiting": {"min_delay": 0, "max_delay": 0},
        "output": {"generate_resume": False, "generate_cover_letter": False, "style": "Classic"},
    }))
    (tmp_path / "plain_text_resume.yaml").write_text("personal_information:\n  name: Test\n  surname: User")
    (tmp_path / "output").mkdir()
    (tmp_path / "crawled_jobs.json").write_text("{}")
    return tmp_path


@patch("src.crawlers.runner.Resume")
@patch("src.crawlers.runner.init_crawler_browser")
@patch("src.crawlers.linkedin.LinkedInCrawler.login")
@patch("src.crawlers.linkedin.LinkedInCrawler.search_jobs")
@patch("src.crawlers.linkedin.LinkedInCrawler.scrape_job")
def test_runner_crawls_and_tracks_jobs(mock_scrape, mock_search, mock_login, mock_browser, mock_resume, tmp_path):
    from src.crawlers.runner import run
    from src.job import Job

    data_folder = _setup_data_folder(tmp_path)

    mock_driver = MagicMock()
    mock_browser.return_value = mock_driver
    mock_resume.return_value = MagicMock()

    mock_search.return_value = [
        {"id": "linkedin_1", "url": "http://job1", "role": "Engineer", "company": "Co1"},
    ]
    job = Job(role="Engineer", company="Co1", location="NYC", link="http://job1", description="Great job")
    mock_scrape.return_value = job

    run(data_folder=str(data_folder))

    mock_login.assert_called_once()
    mock_search.assert_called_once()
    mock_scrape.assert_called_once_with("http://job1")

    # Verify tracker recorded the job
    tracker_data = json.loads((data_folder / "crawled_jobs.json").read_text())
    assert "linkedin_1" in tracker_data
