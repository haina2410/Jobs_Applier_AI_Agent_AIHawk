# LinkedIn Jobs Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a plugin-based job crawler that searches LinkedIn for jobs matching user-defined filters, deduplicates across runs, and automatically generates tailored resumes/cover letters.

**Architecture:** Abstract `BaseCrawler` with `LinkedInCrawler` implementation. JSON-based dedup tracker. Runner entry point that wires crawlers to the existing `ResumeFacade` pipeline. Prerequisite changes to `ResumeFacade` to support headless/automated operation (no interactive prompts, no driver.quit per PDF).

**Tech Stack:** Python, Selenium/undetected-chromedriver (existing), PyYAML (existing), loguru (existing)

**Spec:** `docs/superpowers/specs/2026-03-22-linkedin-crawler-design.md`

---

## File Structure

### New files
- `src/crawlers/__init__.py` — package init, exports `LinkedInCrawler`, `Tracker`, `run`
- `src/crawlers/base.py` — `BaseCrawler` abstract class
- `src/crawlers/linkedin.py` — `LinkedInCrawler` implementation
- `src/crawlers/tracker.py` — JSON-based dedup `Tracker` class
- `src/crawlers/runner.py` — entry point, orchestrates crawl → generate pipeline
- `src/crawlers/config.py` — `CrawlerConfig` loader/validator
- `data_folder_example/crawler_config.yaml` — example config
- `tests/test_tracker.py` — unit tests for Tracker
- `tests/test_crawler_config.py` — unit tests for CrawlerConfig
- `tests/test_linkedin_crawler.py` — unit tests for LinkedInCrawler (mocked Selenium)
- `tests/test_runner.py` — integration test for runner flow

### Modified files
- `src/libs/resume_and_cover_builder/resume_facade.py` — remove `driver.quit()` from PDF methods, add `set_job()` method
- `data_folder_example/secrets.yaml` — add `linkedin_cookies` example

---

### Task 1: Prerequisite — Remove driver.quit() from ResumeFacade PDF methods

**Files:**
- Modify: `src/libs/resume_and_cover_builder/resume_facade.py:88-153`

- [ ] **Step 1: Remove driver.quit() from create_resume_pdf_job_tailored**

In `resume_facade.py`, remove `self.driver.quit()` at line 108. The caller is responsible for driver lifecycle.

```python
# Line 107-108, change from:
        result = HTML_to_PDF(html_resume, self.driver)
        self.driver.quit()
        return result, suggested_name

# To:
        result = HTML_to_PDF(html_resume, self.driver)
        return result, suggested_name
```

- [ ] **Step 2: Remove driver.quit() from create_resume_pdf**

Remove `self.driver.quit()` at line 128.

```python
# Line 127-128, change from:
        result = HTML_to_PDF(html_resume, self.driver)
        self.driver.quit()
        return result

# To:
        result = HTML_to_PDF(html_resume, self.driver)
        return result
```

- [ ] **Step 3: Remove driver.quit() from create_cover_letter**

Remove `self.driver.quit()` at line 152.

```python
# Line 151-152, change from:
        result = HTML_to_PDF(cover_letter_html, self.driver)
        self.driver.quit()
        return result, suggested_name

# To:
        result = HTML_to_PDF(cover_letter_html, self.driver)
        return result, suggested_name
```

- [ ] **Step 4: Add driver.quit() in finally blocks in main.py**

Each caller in `main.py` that creates a driver should quit it in a `finally` block to ensure cleanup on both success and error paths. Wrap the driver usage in each function:

For `create_cover_letter` function — wrap from `driver = init_browser()` (~line 263) through the end of the try block:
```python
        driver = init_browser()
        try:
            resume_generator.set_resume_object(resume_object)
            resume_facade = ResumeFacade(...)
            resume_facade.set_driver(driver)
            resume_facade.link_to_job(job_url)
            result_base64, suggested_name = resume_facade.create_cover_letter()
        finally:
            driver.quit()
```

Apply the same `try/finally` pattern in `create_resume_pdf_job_tailored` (~line 348) and `create_resume_pdf` (~line 433).

- [ ] **Step 5: Add set_job() method to ResumeFacade**

Add a method to set a Job directly without URL navigation, after the `set_driver` method (~line 41):

```python
    def set_job(self, job):
        """Set job directly without URL navigation (used by crawler)."""
        self.job = job
```

- [ ] **Step 6: Commit**

```bash
git add src/libs/resume_and_cover_builder/resume_facade.py main.py
git commit -m "refactor: move driver.quit() to callers, add set_job() to ResumeFacade"
```

---

### Task 2: Tracker — JSON-based dedup

**Files:**
- Create: `src/crawlers/__init__.py`
- Create: `src/crawlers/tracker.py`
- Create: `tests/test_tracker.py`

- [ ] **Step 1: Write failing tests for Tracker**

```python
# tests/test_tracker.py
import json
import tempfile
from pathlib import Path
from src.crawlers.tracker import Tracker


def test_filter_unseen_returns_new_jobs():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"linkedin_111": {"url": "http://old", "role": "Old", "crawled_at": "2026-01-01T00:00:00"}}, f)
        path = Path(f.name)
    tracker = Tracker(path)
    results = [
        {"id": "linkedin_111", "url": "http://old", "role": "Old"},
        {"id": "linkedin_222", "url": "http://new", "role": "New"},
    ]
    unseen = tracker.filter_unseen(results)
    assert len(unseen) == 1
    assert unseen[0]["id"] == "linkedin_222"
    path.unlink()


def test_mark_seen_persists():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({}, f)
        path = Path(f.name)
    tracker = Tracker(path)
    tracker.mark_seen("linkedin_333", "http://example.com")
    # Reload from disk
    tracker2 = Tracker(path)
    assert "linkedin_333" in tracker2.seen
    path.unlink()


def test_empty_file_creates_fresh_tracker():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = Path(f.name)
    tracker = Tracker(path)
    assert tracker.seen == {}
    path.unlink()


def test_nonexistent_file_creates_fresh_tracker(tmp_path):
    path = tmp_path / "does_not_exist.json"
    tracker = Tracker(path)
    assert tracker.seen == {}
    tracker.mark_seen("linkedin_1", "http://example.com")
    assert path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tracker.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Create package init**

```python
# src/crawlers/__init__.py
```

- [ ] **Step 4: Implement Tracker**

```python
# src/crawlers/tracker.py
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.logging import logger


class Tracker:
    """Tracks seen jobs in a JSON file to avoid reprocessing across runs."""

    def __init__(self, path: Path):
        self.path = path
        self.seen = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            text = self.path.read_text()
            if not text.strip():
                return {}
            return json.loads(text)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load tracker file {self.path}: {e}")
            return {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.seen, indent=2))
        tmp.rename(self.path)

    def filter_unseen(self, results: list[dict]) -> list[dict]:
        return [r for r in results if r["id"] not in self.seen]

    def mark_seen(self, job_id: str, url: str, role: str = ""):
        self.seen[job_id] = {
            "url": url,
            "role": role,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_tracker.py -v`
Expected: All 4 PASS

- [ ] **Step 6: Commit**

```bash
git add src/crawlers/__init__.py src/crawlers/tracker.py tests/test_tracker.py
git commit -m "feat: add Tracker for JSON-based job dedup"
```

---

### Task 3: CrawlerConfig — config loading and validation

**Files:**
- Create: `src/crawlers/config.py`
- Create: `tests/test_crawler_config.py`
- Create: `data_folder_example/crawler_config.yaml`

- [ ] **Step 1: Create example config file**

```yaml
# data_folder_example/crawler_config.yaml
enabled_crawlers:
  - linkedin

linkedin:
  filters:
    keywords: "Software Engineer"
    location: "San Francisco, CA"
    experience_level: ["mid-senior", "director"]
    job_type: ["full-time"]
    work_type: ["remote", "hybrid"]
    date_posted: "past_week"
  max_jobs_per_run: 20
  max_pages: 3

rate_limiting:
  min_delay: 2
  max_delay: 5

output:
  generate_resume: true
  generate_cover_letter: true
  style: "Classic"
```

- [ ] **Step 2: Write failing tests for CrawlerConfig**

```python
# tests/test_crawler_config.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_crawler_config.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: Implement CrawlerConfig**

```python
# src/crawlers/config.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CrawlerConfig:
    enabled_crawlers: list[str]
    linkedin: dict[str, Any] = field(default_factory=dict)
    rate_limiting: dict[str, Any] = field(default_factory=lambda: {"min_delay": 2, "max_delay": 5})
    output: dict[str, Any] = field(default_factory=lambda: {
        "generate_resume": True,
        "generate_cover_letter": True,
        "style": "Classic",
    })

    EXPERIENCE_LEVEL_MAP = {
        "internship": 1,
        "entry": 2,
        "associate": 3,
        "mid-senior": 4,
        "director": 5,
        "executive": 6,
    }

    DATE_POSTED_MAP = {
        "past_24h": "r86400",
        "past_week": "r604800",
        "past_month": "r2592000",
    }

    JOB_TYPE_MAP = {
        "full-time": "F",
        "contract": "C",
        "part-time": "P",
        "temporary": "T",
        "internship": "I",
        "volunteer": "V",
        "other": "O",
    }

    WORK_TYPE_MAP = {
        "on-site": 1,
        "remote": 2,
        "hybrid": 3,
    }

    @classmethod
    def load(cls, path: Path) -> "CrawlerConfig":
        if not path.exists():
            raise FileNotFoundError(f"Crawler config not found: {path}")
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        if not data or "enabled_crawlers" not in data:
            raise ValueError("Crawler config must contain 'enabled_crawlers' key")
        return cls(
            enabled_crawlers=data["enabled_crawlers"],
            linkedin=data.get("linkedin", {}),
            rate_limiting=data.get("rate_limiting", {"min_delay": 2, "max_delay": 5}),
            output=data.get("output", {
                "generate_resume": True,
                "generate_cover_letter": True,
                "style": "Classic",
            }),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_crawler_config.py -v`
Expected: All 5 PASS

- [ ] **Step 6: Commit**

```bash
git add src/crawlers/config.py tests/test_crawler_config.py data_folder_example/crawler_config.yaml
git commit -m "feat: add CrawlerConfig loader with LinkedIn filter mappings"
```

---

### Task 4: BaseCrawler abstract class

**Files:**
- Create: `src/crawlers/base.py`

- [ ] **Step 1: Implement BaseCrawler**

```python
# src/crawlers/base.py
from abc import ABC, abstractmethod
from random import uniform
from time import sleep

from src.job import Job
from src.logging import logger
from src.crawlers.tracker import Tracker


class BaseCrawler(ABC):
    """Abstract base class for job crawlers."""

    def __init__(self, driver, tracker: Tracker, config: dict):
        self.driver = driver
        self.tracker = tracker
        self.config = config

    @abstractmethod
    def login(self) -> None:
        """Authenticate with the platform using cookies."""

    @abstractmethod
    def search_jobs(self, filters: dict) -> list[dict]:
        """Search for jobs. Return list of {id, url, role, company}."""

    @abstractmethod
    def scrape_job(self, job_url: str) -> Job:
        """Scrape full job details from a URL. Return populated Job."""

    def crawl(self, filters: dict) -> list[Job]:
        """Template method: search → dedup → scrape."""
        results = self.search_jobs(filters)
        new_results = self.tracker.filter_unseen(results)
        max_jobs = self.config.get("max_jobs_per_run", 20)
        new_results = new_results[:max_jobs]
        logger.info(f"Found {len(results)} jobs, {len(new_results)} new (limit {max_jobs})")

        min_delay = self.config.get("min_delay", 2)
        max_delay = self.config.get("max_delay", 5)
        jobs = []
        for i, result in enumerate(new_results):
            logger.info(f"Scraping job {i+1}/{len(new_results)}: {result.get('role', 'unknown')}")
            try:
                job = self.scrape_job(result["url"])
                jobs.append(job)
            except Exception as e:
                logger.error(f"Failed to scrape {result['url']}: {e}")
            self.tracker.mark_seen(result["id"], result["url"], result.get("role", ""))
            if i < len(new_results) - 1:
                delay = uniform(min_delay, max_delay)
                logger.debug(f"Waiting {delay:.1f}s before next request")
                sleep(delay)
        return jobs
```

- [ ] **Step 2: Commit**

```bash
git add src/crawlers/base.py
git commit -m "feat: add BaseCrawler abstract class with template crawl method"
```

---

### Task 5: LinkedInCrawler implementation

**Files:**
- Create: `src/crawlers/linkedin.py`
- Create: `tests/test_linkedin_crawler.py`

- [ ] **Step 1: Write failing tests for LinkedInCrawler**

```python
# tests/test_linkedin_crawler.py
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

from src.crawlers.linkedin import LinkedInCrawler
from src.crawlers.tracker import Tracker
from src.crawlers.config import CrawlerConfig
from src.job import Job


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


def test_login_injects_cookie(mock_driver, tracker, config):
    crawler = LinkedInCrawler(mock_driver, tracker, config, li_at_cookie="fake_cookie")
    # Mock the login validation
    mock_driver.find_elements.return_value = [MagicMock()]
    crawler.login()
    mock_driver.add_cookie.assert_called_once()
    cookie = mock_driver.add_cookie.call_args[0][0]
    assert cookie["name"] == "li_at"
    assert cookie["value"] == "fake_cookie"


def test_login_raises_on_expired_cookie(mock_driver, tracker, config):
    crawler = LinkedInCrawler(mock_driver, tracker, config, li_at_cookie="expired")
    mock_driver.find_elements.return_value = []
    with pytest.raises(RuntimeError, match="cookie"):
        crawler.login()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_linkedin_crawler.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement LinkedInCrawler**

```python
# src/crawlers/linkedin.py
from urllib.parse import urlencode, quote

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.job import Job
from src.logging import logger
from src.crawlers.base import BaseCrawler
from src.crawlers.config import CrawlerConfig
from src.crawlers.tracker import Tracker


class LinkedInCrawler(BaseCrawler):
    """Crawls LinkedIn job search results."""

    BASE_URL = "https://www.linkedin.com/jobs/search/?"
    JOBS_PER_PAGE = 25

    def __init__(self, driver, tracker: Tracker, config: dict, li_at_cookie: str):
        super().__init__(driver, tracker, config)
        self.li_at_cookie = li_at_cookie

    def login(self) -> None:
        logger.info("Logging into LinkedIn via cookie...")
        self.driver.get("https://www.linkedin.com")
        self.driver.add_cookie({
            "name": "li_at",
            "value": self.li_at_cookie,
            "domain": ".linkedin.com",
        })
        self.driver.get("https://www.linkedin.com/feed/")
        # Validate login by checking for a logged-in indicator
        indicators = self.driver.find_elements(By.CSS_SELECTOR, ".feed-identity-module, .global-nav__me")
        if not indicators:
            raise RuntimeError(
                "LinkedIn login failed — li_at cookie may be expired. "
                "Please refresh your li_at cookie in secrets.yaml."
            )
        logger.info("LinkedIn login successful")

    @staticmethod
    def build_search_url(filters: dict) -> str:
        params = {}
        if "keywords" in filters:
            params["keywords"] = filters["keywords"]
        if "location" in filters:
            params["location"] = filters["location"]
        if "experience_level" in filters:
            codes = [str(CrawlerConfig.EXPERIENCE_LEVEL_MAP[lvl]) for lvl in filters["experience_level"]
                     if lvl in CrawlerConfig.EXPERIENCE_LEVEL_MAP]
            if codes:
                params["f_E"] = ",".join(codes)
        if "job_type" in filters:
            codes = [CrawlerConfig.JOB_TYPE_MAP[jt] for jt in filters["job_type"]
                     if jt in CrawlerConfig.JOB_TYPE_MAP]
            if codes:
                params["f_JT"] = ",".join(codes)
        if "work_type" in filters:
            codes = [str(CrawlerConfig.WORK_TYPE_MAP[wt]) for wt in filters["work_type"]
                     if wt in CrawlerConfig.WORK_TYPE_MAP]
            if codes:
                params["f_WT"] = ",".join(codes)
        if "date_posted" in filters:
            tpr = CrawlerConfig.DATE_POSTED_MAP.get(filters["date_posted"])
            if tpr:
                params["f_TPR"] = tpr
        return "https://www.linkedin.com/jobs/search/?" + urlencode(params)

    def search_jobs(self, filters: dict) -> list[dict]:
        max_pages = self.config.get("max_pages", 3)
        all_results = []

        for page in range(max_pages):
            url = self.build_search_url(filters) + f"&start={page * self.JOBS_PER_PAGE}"
            logger.info(f"Searching LinkedIn page {page + 1}/{max_pages}: {url}")
            self.driver.get(url)

            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".job-card-container, .jobs-search-results-list"))
                )
            except Exception:
                logger.warning(f"No job cards found on page {page + 1}, stopping pagination")
                break

            job_cards = self.driver.find_elements(By.CSS_SELECTOR, ".job-card-container")
            if not job_cards:
                logger.info(f"No jobs on page {page + 1}, stopping pagination")
                break

            for card in job_cards:
                try:
                    job_id = card.get_attribute("data-job-id")
                    if not job_id:
                        continue
                    title_el = card.find_element(By.CSS_SELECTOR, ".job-card-list__title, .job-card-container__link")
                    role = title_el.text.strip()
                    link = title_el.get_attribute("href")
                    company_el = card.find_element(By.CSS_SELECTOR, ".job-card-container__primary-description, .job-card-container__company-name")
                    company = company_el.text.strip()

                    all_results.append({
                        "id": f"linkedin_{job_id}",
                        "url": link.split("?")[0] if link else f"https://www.linkedin.com/jobs/view/{job_id}",
                        "role": role,
                        "company": company,
                    })
                except Exception as e:
                    logger.debug(f"Failed to parse job card: {e}")
                    continue

            logger.info(f"Found {len(job_cards)} cards on page {page + 1}")

        logger.info(f"Total search results: {len(all_results)}")
        return all_results

    def scrape_job(self, job_url: str) -> Job:
        logger.info(f"Scraping job details: {job_url}")
        self.driver.get(job_url)

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-description, .jobs-unified-top-card"))
            )
        except Exception:
            logger.warning("Job detail page did not load fully")

        job = Job()
        job.link = job_url

        # Extract role
        try:
            role_el = self.driver.find_element(By.CSS_SELECTOR, ".jobs-unified-top-card__job-title, .top-card-layout__title")
            job.role = role_el.text.strip()
        except Exception:
            logger.debug("Could not extract role from job page")

        # Extract company
        try:
            company_el = self.driver.find_element(By.CSS_SELECTOR, ".jobs-unified-top-card__company-name, .topcard__org-name-link")
            job.company = company_el.text.strip()
        except Exception:
            logger.debug("Could not extract company from job page")

        # Extract location
        try:
            location_el = self.driver.find_element(By.CSS_SELECTOR, ".jobs-unified-top-card__bullet, .topcard__flavor--bullet")
            job.location = location_el.text.strip()
        except Exception:
            logger.debug("Could not extract location from job page")

        # Extract description
        try:
            desc_el = self.driver.find_element(By.CSS_SELECTOR, ".jobs-description__content, .jobs-description-content")
            job.description = desc_el.text.strip()
        except Exception:
            logger.warning("Could not extract job description")

        return job
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_linkedin_crawler.py -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/crawlers/base.py src/crawlers/linkedin.py tests/test_linkedin_crawler.py
git commit -m "feat: add LinkedInCrawler with search, scrape, and cookie auth"
```

---

### Task 6: Runner — entry point

**Files:**
- Create: `src/crawlers/runner.py`
- Modify: `data_folder_example/secrets.yaml`

- [ ] **Step 1: Update example secrets.yaml**

Add LinkedIn cookies section:

```yaml
llm_api_key: 'your-api-key-here'

linkedin_cookies:
  li_at: "your_li_at_cookie_value"
```

- [ ] **Step 2: Implement runner**

```python
# src/crawlers/runner.py
import base64
from pathlib import Path

import yaml

from src.logging import logger
from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
from src.resume_schemas.resume import Resume
from src.utils.chrome_utils import init_browser
from src.crawlers.config import CrawlerConfig
from src.crawlers.tracker import Tracker
from src.crawlers.linkedin import LinkedInCrawler


def _load_secrets(secrets_path: Path) -> dict:
    with open(secrets_path, "r") as f:
        return yaml.safe_load(f)


def _save_job_output(job, pdf_data: bytes, output_dir: Path, filename: str):
    job_dir = output_dir / f"{job.company}_{job.role}".replace(" ", "_").replace("/", "_")[:80]
    job_dir.mkdir(parents=True, exist_ok=True)
    output_path = job_dir / filename
    with open(output_path, "wb") as f:
        f.write(pdf_data)
    logger.info(f"Saved {filename} to {output_path}")
    return output_path


def run(data_folder: str = "data_folder"):
    data_path = Path(data_folder)

    # Load configs
    config = CrawlerConfig.load(data_path / "crawler_config.yaml")
    secrets = _load_secrets(data_path / "secrets.yaml")
    llm_api_key = secrets.get("llm_api_key", "")

    # Load resume
    resume_path = data_path / "plain_text_resume.yaml"
    with open(resume_path, "r", encoding="utf-8") as f:
        plain_text_resume = f.read()
    resume_object = Resume(plain_text_resume)

    # Init tracker
    tracker = Tracker(data_path / "crawled_jobs.json")

    # Init crawl driver
    crawl_driver = init_browser()

    all_jobs = []
    try:
        for crawler_name in config.enabled_crawlers:
            if crawler_name == "linkedin":
                li_cookies = secrets.get("linkedin_cookies", {})
                li_at = li_cookies.get("li_at", "")
                if not li_at:
                    logger.error("Missing linkedin_cookies.li_at in secrets.yaml, skipping LinkedIn")
                    continue

                crawler_config = {
                    **config.linkedin,
                    "min_delay": config.rate_limiting.get("min_delay", 2),
                    "max_delay": config.rate_limiting.get("max_delay", 5),
                }
                crawler = LinkedInCrawler(crawl_driver, tracker, crawler_config, li_at_cookie=li_at)

                try:
                    crawler.login()
                    jobs = crawler.crawl(config.linkedin.get("filters", {}))
                    all_jobs.extend(jobs)
                    logger.info(f"LinkedIn: found {len(jobs)} new jobs")
                except Exception as e:
                    logger.error(f"LinkedIn crawler failed: {e}")
            else:
                logger.warning(f"Unknown crawler: {crawler_name}, skipping")
    finally:
        crawl_driver.quit()

    if not all_jobs:
        logger.info("No new jobs found. Done.")
        return

    # Generate resumes/cover letters
    output_dir = data_path / "output"
    output_dir.mkdir(exist_ok=True)
    style_name = config.output.get("style", "Classic")

    generated = 0
    for job in all_jobs:
        logger.info(f"Generating documents for: {job.role} at {job.company}")
        pdf_driver = init_browser()
        try:
            style_manager = StyleManager()
            style_manager.set_selected_style(style_name)
            resume_generator = ResumeGenerator()
            facade = ResumeFacade(
                api_key=llm_api_key,
                style_manager=style_manager,
                resume_generator=resume_generator,
                resume_object=resume_object,
                output_path=output_dir,
            )
            facade.set_driver(pdf_driver)
            facade.set_job(job)

            if config.output.get("generate_resume", True):
                result_base64, _ = facade.create_resume_pdf_job_tailored()
                pdf_data = base64.b64decode(result_base64)
                _save_job_output(job, pdf_data, output_dir, "resume_tailored.pdf")

            if config.output.get("generate_cover_letter", True):
                cover_base64, _ = facade.create_cover_letter()
                pdf_data = base64.b64decode(cover_base64)
                _save_job_output(job, pdf_data, output_dir, "cover_letter.pdf")

            generated += 1
        except Exception as e:
            logger.error(f"Failed to generate documents for {job.role} at {job.company}: {e}")
        finally:
            pdf_driver.quit()

    logger.info(f"Done. Generated documents for {generated}/{len(all_jobs)} jobs.")


if __name__ == "__main__":
    run()
```

- [ ] **Step 3: Update crawlers __init__.py**

```python
# src/crawlers/__init__.py
from src.crawlers.linkedin import LinkedInCrawler
from src.crawlers.tracker import Tracker
from src.crawlers.runner import run
```

- [ ] **Step 4: Commit**

```bash
git add src/crawlers/runner.py src/crawlers/__init__.py data_folder_example/secrets.yaml
git commit -m "feat: add crawler runner entry point"
```

---

### Task 7: Integration test

**Files:**
- Create: `tests/test_runner.py`

- [ ] **Step 1: Write integration test with mocked browser**

```python
# tests/test_runner.py
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import yaml
import pytest


def _setup_data_folder(tmp_path):
    """Create a minimal data_folder for testing."""
    # secrets
    (tmp_path / "secrets.yaml").write_text(yaml.dump({
        "llm_api_key": "test-key",
        "linkedin_cookies": {"li_at": "test-cookie"},
    }))
    # crawler config
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
    # plain text resume
    (tmp_path / "plain_text_resume.yaml").write_text("personal_information:\n  name: Test\n  surname: User")
    # output dir
    (tmp_path / "output").mkdir()
    # tracker
    (tmp_path / "crawled_jobs.json").write_text("{}")
    return tmp_path


@patch("src.crawlers.runner.Resume")
@patch("src.crawlers.runner.init_browser")
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
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_runner.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_runner.py
git commit -m "test: add integration test for crawler runner"
```

---

### Task 8: Final cleanup and documentation

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Commit any remaining changes (if any)**

Review `git status` and stage only relevant files explicitly before committing.
