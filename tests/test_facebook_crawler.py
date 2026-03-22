import hashlib
import json
from unittest.mock import MagicMock, patch
import pytest

from src.crawlers.facebook import FacebookCrawler
from src.crawlers.tracker import Tracker
from src.job import Job


@pytest.fixture
def tracker(tmp_path):
    path = tmp_path / "crawled_jobs.json"
    path.write_text("{}")
    return Tracker(path)


@pytest.fixture
def mock_driver():
    return MagicMock()


@pytest.fixture
def config():
    return {
        "group_urls": ["https://www.facebook.com/groups/test123"],
        "cookies_file": "cookies.json",
        "target_posts": 5,
        "max_pages": 3,
        "filter_remote_only": False,
        "min_delay": 0,
        "max_delay": 0,
    }


@pytest.fixture
def cookies():
    return [{"name": "c_user", "value": "123", "domain": ".facebook.com"}]


def test_mbasic_url_conversion():
    assert FacebookCrawler._to_mbasic_url("https://www.facebook.com/groups/test123") == "https://mbasic.facebook.com/groups/test123"


def test_mbasic_url_already_mbasic():
    assert FacebookCrawler._to_mbasic_url("https://mbasic.facebook.com/groups/test123") == "https://mbasic.facebook.com/groups/test123"


def test_generate_post_id():
    text = "Looking for Senior Python Developer"
    post_id = FacebookCrawler._generate_post_id(text)
    expected = "facebook_" + hashlib.md5(text.encode()).hexdigest()[:16]
    assert post_id == expected


def test_login_injects_cookies(mock_driver, tracker, config, cookies):
    crawler = FacebookCrawler(mock_driver, tracker, config, cookies=cookies, llm_api_key="test")
    mock_driver.find_elements.return_value = [MagicMock()]
    mock_driver.current_url = "https://mbasic.facebook.com/me"
    mock_driver.page_source = "<div>Profile content</div>"
    crawler.login()
    assert mock_driver.add_cookie.call_count == 1


def test_login_raises_on_failure(mock_driver, tracker, config, cookies):
    crawler = FacebookCrawler(mock_driver, tracker, config, cookies=cookies, llm_api_key="test")
    mock_driver.find_elements.return_value = []
    mock_driver.current_url = "https://mbasic.facebook.com/login"
    mock_driver.page_source = "<form id='login_form'>"
    with pytest.raises(RuntimeError, match="Facebook login failed"):
        crawler.login()


@patch("src.crawlers.facebook.FacebookCrawler._llm_extract_job_fields")
def test_scrape_job_from_cache(mock_extract, mock_driver, tracker, config, cookies):
    crawler = FacebookCrawler(mock_driver, tracker, config, cookies=cookies, llm_api_key="test")
    post_text = "Hiring Python Dev at ACME Corp, remote, 50M VND"
    job_id = FacebookCrawler._generate_post_id(post_text)
    crawler._post_cache[job_id] = post_text

    mock_extract.return_value = {
        "role": "Python Dev",
        "company": "ACME Corp",
        "location": "Remote",
        "description": post_text,
    }

    job = crawler.scrape_job(job_id)
    assert job.role == "Python Dev"
    assert job.company == "ACME Corp"
    assert job.description == post_text
