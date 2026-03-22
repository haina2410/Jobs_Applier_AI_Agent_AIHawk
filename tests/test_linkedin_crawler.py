from unittest.mock import MagicMock
import pytest

from src.crawlers.linkedin import LinkedInCrawler
from src.crawlers.tracker import Tracker


@pytest.fixture
def tracker(tmp_path):
    path = tmp_path / "crawled_jobs.json"
    path.write_text("{}")
    return Tracker(path)


@pytest.fixture
def mock_driver():
    driver = MagicMock()
    driver.get = MagicMock()
    driver.add_cookie = MagicMock()
    driver.find_elements = MagicMock(return_value=[])
    return driver


@pytest.fixture
def config():
    return {
        "filters": {
            "keywords": "Engineer",
            "location": "NYC",
            "experience_level": ["mid-senior"],
            "job_type": ["full-time"],
            "work_type": ["remote"],
            "date_posted": "past_week",
        },
        "max_jobs_per_run": 5,
        "max_pages": 1,
        "min_delay": 0,
        "max_delay": 0,
    }


def test_build_search_url():
    url = LinkedInCrawler.build_search_url({
        "keywords": "Software Engineer",
        "location": "San Francisco",
        "experience_level": ["mid-senior", "director"],
        "job_type": ["full-time"],
        "work_type": ["remote"],
        "date_posted": "past_week",
    })
    assert "keywords=Software+Engineer" in url or "keywords=Software%20Engineer" in url
    assert "location=San" in url
    assert "f_E=4%2C5" in url or "f_E=4,5" in url
    assert "f_JT=F" in url
    assert "f_WT=2" in url
    assert "f_TPR=r604800" in url


def test_login_injects_cookies(mock_driver, tracker, config):
    cookies = {"li_at": "fake_cookie", "li_rm": "remember_me"}
    crawler = LinkedInCrawler(mock_driver, tracker, config, cookies=cookies)
    mock_driver.find_elements.return_value = [MagicMock()]
    crawler.login()
    assert mock_driver.add_cookie.call_count == 2
    injected = {call[0][0]["name"]: call[0][0]["value"] for call in mock_driver.add_cookie.call_args_list}
    assert injected["li_at"] == "fake_cookie"
    assert injected["li_rm"] == "remember_me"


def test_login_succeeds_via_url_check(mock_driver, tracker, config):
    """Login succeeds when URL contains /feed even if no CSS selectors match."""
    cookies = {"li_at": "valid_cookie"}
    crawler = LinkedInCrawler(mock_driver, tracker, config, cookies=cookies)
    mock_driver.find_elements.return_value = []
    mock_driver.current_url = "https://www.linkedin.com/feed/"
    crawler.login()  # Should not raise


def test_login_raises_on_redirect_to_login(mock_driver, tracker, config):
    cookies = {"li_at": "expired"}
    crawler = LinkedInCrawler(mock_driver, tracker, config, cookies=cookies)
    mock_driver.find_elements.return_value = []
    mock_driver.current_url = "https://www.linkedin.com/login"
    with pytest.raises(RuntimeError, match="cookie"):
        crawler.login()
