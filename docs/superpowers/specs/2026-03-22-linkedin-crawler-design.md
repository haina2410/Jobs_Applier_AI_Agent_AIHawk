# LinkedIn Jobs Crawler Design

## Overview

Add a plugin-based job crawling system to AIHawk. The first implementation targets LinkedIn job search. The architecture supports future crawlers (Facebook group posts, etc.) via a shared base class. The crawler runs on a schedule (cron), searches for jobs matching user-defined filters, deduplicates against previously seen jobs, scrapes full details, and automatically generates tailored resumes/cover letters using the existing pipeline.

## Module Structure

```
src/crawlers/
├── __init__.py
├── base.py              # BaseCrawler abstract class
├── linkedin.py          # LinkedInCrawler
├── facebook.py          # FacebookCrawler (future, not implemented now)
├── tracker.py           # JSON-based dedup tracking
├── runner.py            # Entry point for scheduled runs
└── config.py            # Crawler-specific config loading
```

Placed under `src/` for consistency with the existing codebase.

## BaseCrawler Interface

```python
class BaseCrawler(ABC):
    def __init__(self, driver, tracker, config):
        self.driver = driver
        self.tracker = tracker
        self.config = config

    @abstractmethod
    def login(self) -> None:
        """Authenticate using cookies from secrets.yaml"""

    @abstractmethod
    def search_jobs(self, filters: dict) -> list[dict]:
        """Return list of {id, url, role, company} from search results"""

    @abstractmethod
    def scrape_job(self, job_url: str) -> Job:
        """Navigate to job URL, extract full details, return Job dataclass"""

    def crawl(self, filters: dict) -> list[Job]:
        """Template method: search → dedup → scrape full details"""
        results = self.search_jobs(filters)
        new_results = self.tracker.filter_unseen(results)
        new_results = new_results[:self.config.get("max_jobs_per_run", 20)]
        jobs = []
        for result in new_results:
            sleep(uniform(self.config["min_delay"], self.config["max_delay"]))
            try:
                job = self.scrape_job(result["url"])
                jobs.append(job)
            except Exception as e:
                logger.error(f"Failed to scrape {result['url']}: {e}")
            self.tracker.mark_seen(result["id"], result["url"])
        return jobs
```

Key design decisions:
- `max_jobs_per_run` enforced by truncating after dedup filtering.
- Failed jobs are always marked as seen to prevent infinite retry loops on permanently broken listings. The error is logged for manual review.
- `search_jobs` returns `role` (not `title`) to match the `Job` dataclass field name.

## LinkedIn Crawler

### Authentication

Cookie-based. User provides `li_at` cookie value in `secrets.yaml`. The crawler injects it via `driver.add_cookie()` after navigating to `linkedin.com`. After injection, navigates to a known page and checks for a logged-in indicator element to validate the cookie is still valid.

```yaml
# secrets.yaml
linkedin_cookies:
  li_at: "your_li_at_cookie_value"
```

If the cookie is expired/invalid, raises an error with a message directing the user to refresh their `li_at` cookie.

### Search

Navigate to `linkedin.com/jobs/search/` with query parameters:

| Filter           | LinkedIn URL param                    | Example                  |
|------------------|---------------------------------------|--------------------------|
| Keywords         | `keywords`                            | `Software+Engineer`      |
| Location         | `location`                            | `San+Francisco`          |
| Experience level | `f_E`                                 | `f_E=4,5`               |
| Job type         | `f_JT` (F=full-time, C=contract, P=part-time, T=temporary, I=internship, V=volunteer, O=other) | `f_JT=F,C` |
| Work type        | `f_WT` (1=on-site, 2=remote, 3=hybrid)| `f_WT=2,3`             |
| Date posted      | `f_TPR` (r86400=24h, r604800=week, r2592000=month) | `f_TPR=r604800` |

Experience level mapping: `{internship: 1, entry: 2, associate: 3, mid-senior: 4, director: 5, executive: 6}`

### Pagination

Use `&start=25` URL parameter to paginate through results. Configurable `max_pages` limit. Stop early if a page returns zero job cards.

### Scraping Search Results

Parse job cards from the LinkedIn DOM. Extract: job ID (from `data-job-id` attribute), role, company, location, URL.

### Scraping Full Job Details

Navigate to individual job URL, wait for description element to render, extract full description HTML. Populate `Job` dataclass fields: role, company, location, link, description.

## Facebook Crawler (Future)

Will crawl configured Facebook groups for job posts. Uses LLM to classify which posts are job listings vs. general discussion, then extracts job details from matching posts. Authentication via Facebook cookies. Not implemented in this phase.

## Tracker

JSON file at `data_folder/crawled_jobs.json`. Key format: `{platform}_{platform_specific_id}` (e.g., `linkedin_12345`).

```json
{
  "linkedin_12345": {
    "url": "https://linkedin.com/jobs/view/12345",
    "role": "Software Engineer",
    "crawled_at": "2026-03-22T10:00:00"
  }
}
```

Methods:
- `filter_unseen(results) -> list[dict]` — return only jobs not in the tracker
- `mark_seen(job_id, url)` — add job to tracker with timestamp
- `load()` / `save()` — read/write JSON file. Write to temp file first, then atomic rename to prevent corruption on crash.

## Configuration

New file `data_folder/crawler_config.yaml`:

```yaml
enabled_crawlers:
  - linkedin

linkedin:
  filters:
    keywords: "Software Engineer"
    location: "San Francisco, CA"
    experience_level: ["mid-senior", "senior"]
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

- `work_type` replaces the ambiguous `remote` boolean — supports `on-site`, `remote`, `hybrid` as a list.
- `output.style` specifies the CSS style name for resume generation, avoiding interactive prompts.

## Runner

Entry point: `python -m src.crawlers.runner`

```
1. Load configs (crawler_config.yaml, secrets.yaml, plain_text_resume.yaml)
2. Validate configs
3. Init Chrome driver via existing chrome_utils.py
4. Init tracker (crawled_jobs.json)
5. For each enabled crawler:
     - Instantiate crawler (shares driver)
     - login()
     - crawl(filters) → list[Job]
6. For each job:
     - Init ResumeFacade with a fresh driver (see prerequisite changes)
     - Set job on facade directly (bypass link_to_job URL navigation)
     - Set style programmatically (bypass interactive prompt)
     - Generate resume/cover letter based on output config
     - Save PDF to data_folder/output/{company}_{role}/
7. Log summary (X new jobs found, Y resumes generated)
8. Cleanup crawling driver
```

Scheduling is external (cron/launchd). No built-in scheduler.

## Prerequisite Changes to Existing Code

These changes to the existing codebase are required before the crawler can integrate:

### 1. ResumeFacade: driver lifecycle

`ResumeFacade.create_resume_pdf_job_tailored()` and `create_cover_letter()` call `self.driver.quit()` at the end. For the crawler's multi-job loop, we need to either:
- **Option A (recommended):** Extract PDF generation into a helper that creates its own temporary driver, generates the PDF, and quits — leaving the crawler's main driver untouched.
- **Option B:** Add a `keep_driver=False` parameter to these methods. The crawler passes `keep_driver=True`.

### 2. ResumeFacade: programmatic style selection

`StyleManager` uses `inquirer` for interactive style selection. Add a `set_style(style_name: str)` method to `ResumeFacade` (or `StyleManager`) that resolves the style path by name without prompting. The crawler passes `output.style` from config.

### 3. Job saving

The existing `ApplicationSaver` references a `JobApplication` class that does not exist in the repo. The crawler will implement its own lightweight save logic: write the generated PDF and a `job_details.json` to `data_folder/output/{company}_{role}/`. This avoids depending on the broken `ApplicationSaver`.

## Rate Limiting

Random delay between `min_delay` and `max_delay` seconds between each page navigation. Configurable in `crawler_config.yaml`.

## Error Handling

- If a single job fails (scraping or resume generation), log the error and continue to the next job. Failed jobs are still marked as seen to prevent infinite retry loops.
- If login fails, log error with cookie refresh instructions and skip that crawler.
- If config is invalid, fail fast with a clear error message.

## Integration Points

- **Chrome driver:** Reuse `src/utils/chrome_utils.py` for browser initialization.
- **Job model:** Use existing `src/job.py` `Job` dataclass.
- **Resume generation:** Use `ResumeFacade` with programmatic style selection and job set directly (no URL navigation).
- **Logging:** Use existing loguru setup from `src/logging.py`.

## Scope

### In scope (this phase)
- `BaseCrawler` abstract class
- `LinkedInCrawler` implementation
- `Tracker` (JSON-based dedup)
- `Runner` entry point
- `crawler_config.yaml` configuration
- Prerequisite changes to `ResumeFacade` and `StyleManager`
- Integration with existing resume/cover letter pipeline

### Out of scope (future)
- Facebook group crawler implementation
- Built-in scheduler
- Proxy rotation
- CAPTCHA solving
