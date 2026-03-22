# Facebook Group Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FacebookCrawler extending BaseCrawler to crawl job posts from Facebook groups via mbasic.facebook.com, classify with LLM, and extract structured Job fields.

**Architecture:** `FacebookCrawler` uses mbasic.facebook.com (pure HTML, no JS) for post extraction, LLM for job classification and field extraction. Integrates with existing runner, tracker, and config.

**Tech Stack:** Python, Selenium/undetected-chromedriver (existing), LangChain (existing for LLM calls), PyYAML (existing)

**Spec:** `docs/superpowers/specs/2026-03-22-facebook-crawler-design.md`

---

## File Structure

### New files
- `src/crawlers/facebook.py` — `FacebookCrawler` class
- `tests/test_facebook_crawler.py` — unit tests

### Modified files
- `src/crawlers/config.py` — add `facebook` field to `CrawlerConfig`
- `src/crawlers/runner.py` — register Facebook crawler
- `src/crawlers/__init__.py` — export `FacebookCrawler`
- `data_folder_example/crawler_config.yaml` — add facebook config example

---

### Task 1: Add facebook field to CrawlerConfig

**Files:**
- Modify: `src/crawlers/config.py`
- Modify: `data_folder_example/crawler_config.yaml`
- Modify: `tests/test_crawler_config.py`

- [ ] **Step 1: Add test for facebook config loading**

Add to `tests/test_crawler_config.py`:

```python
def test_load_config_with_facebook(tmp_path):
    cfg_path = tmp_path / "crawler_config.yaml"
    _write_yaml({
        "enabled_crawlers": ["facebook"],
        "facebook": {
            "group_urls": ["https://www.facebook.com/groups/123"],
            "cookies_file": "facebook.com.cookies.json",
            "target_posts": 25,
            "max_pages": 10,
            "filter_remote_only": False,
        },
        "rate_limiting": {"min_delay": 1, "max_delay": 3},
        "output": {"generate_resume": True, "generate_cover_letter": False, "style": "Default"},
    }, cfg_path)
    config = CrawlerConfig.load(cfg_path)
    assert config.enabled_crawlers == ["facebook"]
    assert config.facebook["group_urls"] == ["https://www.facebook.com/groups/123"]
    assert config.facebook["target_posts"] == 25
    assert config.facebook["filter_remote_only"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_crawler_config.py::test_load_config_with_facebook -v`
Expected: FAIL (facebook field not on CrawlerConfig)

- [ ] **Step 3: Add facebook field to CrawlerConfig**

In `src/crawlers/config.py`, add field after `linkedin`:

```python
    facebook: dict[str, Any] = field(default_factory=dict)
```

And in `load()`, add:

```python
            facebook=data.get("facebook", {}),
```

- [ ] **Step 4: Update example config**

Append to `data_folder_example/crawler_config.yaml`:

```yaml

facebook:
  group_urls:
    - "https://www.facebook.com/groups/your-group-id"
  cookies_file: "facebook.com.cookies.json"
  target_posts: 25
  max_pages: 10
  filter_remote_only: false
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_crawler_config.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/crawlers/config.py data_folder_example/crawler_config.yaml tests/test_crawler_config.py
git commit -m "feat: add facebook config to CrawlerConfig"
```

---

### Task 2: Implement FacebookCrawler

**Files:**
- Create: `src/crawlers/facebook.py`
- Create: `tests/test_facebook_crawler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_facebook_crawler.py
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
    driver = MagicMock()
    return driver


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
    url = "https://www.facebook.com/groups/test123"
    result = FacebookCrawler._to_mbasic_url(url)
    assert result == "https://mbasic.facebook.com/groups/test123"


def test_mbasic_url_already_mbasic():
    url = "https://mbasic.facebook.com/groups/test123"
    result = FacebookCrawler._to_mbasic_url(url)
    assert result == "https://mbasic.facebook.com/groups/test123"


def test_generate_post_id():
    text = "Looking for Senior Python Developer"
    post_id = FacebookCrawler._generate_post_id(text)
    expected = "facebook_" + hashlib.md5(text.encode()).hexdigest()[:16]
    assert post_id == expected


def test_login_injects_cookies(mock_driver, tracker, config, cookies):
    crawler = FacebookCrawler(mock_driver, tracker, config, cookies=cookies, llm_api_key="test")
    # Mock successful login — profile page has content
    mock_driver.find_elements.return_value = [MagicMock()]
    mock_driver.current_url = "https://mbasic.facebook.com/me"
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_facebook_crawler.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement FacebookCrawler**

```python
# src/crawlers/facebook.py
import hashlib
import json
import re
import time
from urllib.parse import urljoin

from selenium.webdriver.common.by import By

from src.job import Job
from src.logging import logger
from src.crawlers.base import BaseCrawler
from src.crawlers.tracker import Tracker

# LLM imports
from langchain_core.messages import HumanMessage, SystemMessage


class FacebookCrawler(BaseCrawler):
    """Crawls Facebook group posts via mbasic.facebook.com."""

    MBASIC_URL = "https://mbasic.facebook.com"

    def __init__(self, driver, tracker: Tracker, config: dict, cookies: list, llm_api_key: str):
        super().__init__(driver, tracker, config)
        self.cookies = cookies
        self.llm_api_key = llm_api_key
        self._post_cache: dict[str, str] = {}  # {job_id: post_text}

    @staticmethod
    def _to_mbasic_url(url: str) -> str:
        """Convert www/m.facebook.com URL to mbasic.facebook.com."""
        return re.sub(r"https://(www\.|m\.)?facebook\.com", "https://mbasic.facebook.com", url)

    @staticmethod
    def _generate_post_id(text: str) -> str:
        return "facebook_" + hashlib.md5(text.encode()).hexdigest()[:16]

    def login(self) -> None:
        logger.info("Logging into Facebook via cookies...")
        self.driver.get(self.MBASIC_URL)
        time.sleep(2)

        for cookie in self.cookies:
            clean = {k: v for k, v in cookie.items() if k in ("name", "value", "domain", "path", "secure", "httpOnly")}
            if "domain" not in clean:
                clean["domain"] = ".facebook.com"
            try:
                self.driver.add_cookie(clean)
            except Exception as e:
                logger.debug(f"Failed to add cookie {clean.get('name')}: {e}")

        self.driver.get(f"{self.MBASIC_URL}/me")
        time.sleep(2)

        # Check for login form — if present, login failed
        if "/login" in self.driver.current_url or "login_form" in self.driver.page_source:
            raise RuntimeError(
                "Facebook login failed — cookies may be expired. "
                "Please re-export your Facebook cookies."
            )
        logger.info("Facebook login successful")

    def search_jobs(self, filters: dict) -> list[dict]:
        group_urls = self.config.get("group_urls", [])
        target_posts = self.config.get("target_posts", 25)
        max_pages = self.config.get("max_pages", 10)
        filter_remote = self.config.get("filter_remote_only", False)

        all_posts = []
        for group_url in group_urls:
            mbasic_url = self._to_mbasic_url(group_url)
            posts = self._crawl_group_posts(mbasic_url, target_posts, max_pages)
            all_posts.extend(posts)
            logger.info(f"Crawled {len(posts)} posts from {group_url}")

        if not all_posts:
            return []

        # LLM classify job posts
        job_posts = self._llm_classify_job_posts(all_posts)
        logger.info(f"LLM classified {len(job_posts)}/{len(all_posts)} posts as job listings")

        # Optional remote filter
        if filter_remote and job_posts:
            job_posts = self._llm_filter_remote(job_posts)
            logger.info(f"After remote filter: {len(job_posts)} posts")

        # Build results and cache
        results = []
        for post in job_posts:
            post_id = self._generate_post_id(post["text"])
            self._post_cache[post_id] = post["text"]
            results.append({
                "id": post_id,
                "url": post.get("group_url", ""),
                "role": "",
                "company": "",
            })
        return results

    def scrape_job(self, job_url: str) -> Job:
        """Extract Job fields from cached post text via LLM.

        Note: job_url is actually the job_id for Facebook posts,
        since we override crawl() to pass the id instead.
        """
        job_id = job_url  # BaseCrawler.crawl() passes result["url"]
        post_text = self._post_cache.get(job_id, "")
        if not post_text:
            logger.warning(f"No cached post text for {job_id}")
            return Job()

        fields = self._llm_extract_job_fields(post_text)

        job = Job()
        job.role = fields.get("role", "")
        job.company = fields.get("company", "")
        job.location = fields.get("location", "")
        job.description = fields.get("description", post_text)
        job.link = ""
        return job

    def crawl(self, filters: dict) -> list[Job]:
        """Override to pass job_id as url for scrape_job lookup."""
        results = self.search_jobs(filters)
        new_results = self.tracker.filter_unseen(results)
        max_jobs = self.config.get("max_jobs_per_run", 20)
        new_results = new_results[:max_jobs]
        logger.info(f"Found {len(results)} jobs, {len(new_results)} new (limit {max_jobs})")

        jobs = []
        for i, result in enumerate(new_results):
            logger.info(f"Extracting job {i+1}/{len(new_results)}")
            try:
                job = self.scrape_job(result["id"])
                jobs.append(job)
            except Exception as e:
                logger.error(f"Failed to extract job from post: {e}")
            self.tracker.mark_seen(result["id"], result["url"], result.get("role", ""))
        return jobs

    # --- Private methods ---

    def _crawl_group_posts(self, mbasic_url: str, target_posts: int, max_pages: int) -> list[dict]:
        """Crawl posts from a mbasic.facebook.com group page."""
        posts = []
        seen_texts = set()
        current_url = mbasic_url

        for page in range(max_pages):
            logger.info(f"Crawling page {page + 1}/{max_pages}: {current_url}")
            self.driver.get(current_url)
            time.sleep(2)

            # Extract post text from mbasic page
            # mbasic.facebook.com renders posts in <div> elements within the feed
            # Posts typically appear in article-like divs or story containers
            post_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[data-ft], div.bx, article")

            if not post_elements:
                # Fallback: try broader selectors
                post_elements = self.driver.find_elements(By.CSS_SELECTOR, "#m_group_stories_container div > div")

            for el in post_elements:
                try:
                    text = el.text.strip()
                    if len(text) < 30 or len(text) > 5000:
                        continue
                    # Dedup within this run
                    text_key = text[:100]
                    if text_key in seen_texts:
                        continue
                    seen_texts.add(text_key)
                    posts.append({"text": text, "group_url": mbasic_url})
                except Exception:
                    continue

            logger.info(f"Page {page + 1}: collected {len(posts)} total posts")

            if len(posts) >= target_posts:
                break

            # Find "See more posts" pagination link
            next_link = self._find_pagination_link()
            if not next_link:
                logger.info("No more pages to crawl")
                break
            current_url = next_link

        return posts[:target_posts]

    def _find_pagination_link(self) -> str | None:
        """Find the 'See more posts' link on mbasic.facebook.com."""
        try:
            # mbasic uses <a> links for pagination
            links = self.driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                text = link.text.strip().lower()
                href = link.get_attribute("href") or ""
                if any(kw in text for kw in ["see more posts", "xem thêm bài viết", "more posts", "xem thêm"]):
                    if href.startswith("http"):
                        return href
                    elif href.startswith("/"):
                        return f"{self.MBASIC_URL}{href}"
        except Exception as e:
            logger.debug(f"Error finding pagination link: {e}")
        return None

    def _get_llm(self):
        """Get LLM instance using existing factory."""
        from src.libs.resume_and_cover_builder.llm.llm_factory import LLMFactory
        return LLMFactory.create_llm(self.llm_api_key)

    def _llm_classify_job_posts(self, posts: list[dict]) -> list[dict]:
        """Use LLM to identify which posts are job listings."""
        if not posts:
            return []

        numbered = "\n\n".join(f"[{i+1}] {p['text'][:500]}" for i, p in enumerate(posts))
        prompt = (
            "Given the numbered Facebook posts below, identify posts that are clearly "
            "job-related (hiring, recruitment, job opening, looking for candidate, job offer). "
            "Return only a JSON array of integers (1-based indexes), with no extra text.\n\n"
            f"{numbered}"
        )

        try:
            llm = self._get_llm()
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            # Extract JSON array from response
            match = re.search(r'\[[\d\s,]*\]', content)
            if match:
                indexes = json.loads(match.group())
                return [posts[i - 1] for i in indexes if 1 <= i <= len(posts)]
        except Exception as e:
            logger.error(f"LLM job classification failed: {e}")

        return []

    def _llm_filter_remote(self, posts: list[dict]) -> list[dict]:
        """Use LLM to filter remote-only jobs."""
        if not posts:
            return []

        numbered = "\n\n".join(f"[{i+1}] {p['text'][:500]}" for i, p in enumerate(posts))
        prompt = (
            "Given the numbered job posts below, identify only jobs that are explicitly remote "
            "(remote/WFH/work from home/any location/fully remote). "
            "Return only a JSON array of integers (1-based indexes), with no extra text.\n\n"
            f"{numbered}"
        )

        try:
            llm = self._get_llm()
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            match = re.search(r'\[[\d\s,]*\]', content)
            if match:
                indexes = json.loads(match.group())
                return [posts[i - 1] for i in indexes if 1 <= i <= len(posts)]
        except Exception as e:
            logger.error(f"LLM remote filter failed: {e}")

        return posts  # Return all if filter fails

    def _llm_extract_job_fields(self, post_text: str) -> dict:
        """Use LLM to extract structured job fields from post text."""
        prompt = (
            "Extract structured job information from this Facebook post. "
            "Return JSON with these fields:\n"
            '- role: job title/position\n'
            '- company: company name\n'
            '- location: job location\n'
            '- description: full job description\n\n'
            "If a field cannot be determined, use empty string. "
            "Return only valid JSON, no extra text.\n\n"
            f"Post:\n{post_text}"
        )

        try:
            llm = self._get_llm()
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            # Extract JSON from response (may have markdown fences)
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            return json.loads(content)
        except Exception as e:
            logger.error(f"LLM field extraction failed: {e}")
            return {"role": "", "company": "", "location": "", "description": post_text}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_facebook_crawler.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/crawlers/facebook.py tests/test_facebook_crawler.py
git commit -m "feat: add FacebookCrawler with mbasic parsing and LLM classification"
```

---

### Task 3: Integrate Facebook crawler into runner

**Files:**
- Modify: `src/crawlers/runner.py`
- Modify: `src/crawlers/__init__.py`

- [ ] **Step 1: Add Facebook import and handler to runner.py**

In `src/crawlers/runner.py`, add import:
```python
from src.crawlers.facebook import FacebookCrawler
```

Add `import json` at the top (already has `import base64`).

In the `for crawler_name in config.enabled_crawlers` loop, after the LinkedIn block and before the `else`, add:

```python
            elif crawler_name == "facebook":
                fb_config = config.facebook
                cookies_file = fb_config.get("cookies_file", "facebook.com.cookies.json")
                cookies_path = data_path / cookies_file
                if not cookies_path.exists():
                    logger.error(f"Facebook cookies file not found: {cookies_path}, skipping")
                    continue
                try:
                    fb_cookies = json.loads(cookies_path.read_text())
                    if isinstance(fb_cookies, dict) and "cookies" in fb_cookies:
                        fb_cookies = fb_cookies["cookies"]
                except (json.JSONDecodeError, OSError) as e:
                    logger.error(f"Failed to load Facebook cookies: {e}, skipping")
                    continue

                crawler_config = {
                    **fb_config,
                    "min_delay": config.rate_limiting.get("min_delay", 2),
                    "max_delay": config.rate_limiting.get("max_delay", 5),
                }
                crawler = FacebookCrawler(
                    crawl_driver, tracker, crawler_config,
                    cookies=fb_cookies, llm_api_key=llm_api_key,
                )

                try:
                    crawler.login()
                    jobs = crawler.crawl(fb_config)
                    all_jobs.extend(jobs)
                    logger.info(f"Facebook: found {len(jobs)} new jobs")
                except Exception as e:
                    logger.error(f"Facebook crawler failed: {e}")
```

- [ ] **Step 2: Update __init__.py**

```python
from src.crawlers.linkedin import LinkedInCrawler
from src.crawlers.facebook import FacebookCrawler
from src.crawlers.tracker import Tracker
from src.crawlers.runner import run
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/crawlers/runner.py src/crawlers/__init__.py
git commit -m "feat: integrate FacebookCrawler into runner"
```

---

### Task 4: Update docs and final cleanup

- [ ] **Step 1: Update CLAUDE.md**

Add Facebook crawler info to the Crawlers section.

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Facebook crawler to CLAUDE.md"
```
