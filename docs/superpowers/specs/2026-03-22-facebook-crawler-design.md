# Facebook Group Jobs Crawler Design

## Overview

Add a `FacebookCrawler` extending the existing `BaseCrawler` abstract class. Crawls Facebook group posts via `mbasic.facebook.com` (lightweight HTML, no JS), uses LLM to classify which posts are job listings, then LLM extracts structured Job fields from each post. Integrates with the existing runner pipeline for automated resume/cover letter generation.

## FacebookCrawler Class

```python
class FacebookCrawler(BaseCrawler):
    MBASIC_URL = "https://mbasic.facebook.com"

    def __init__(self, driver, tracker, config, cookies, llm_api_key):
        super().__init__(driver, tracker, config)
        self.cookies = cookies          # list[dict] from JSON file
        self.llm_api_key = llm_api_key
        self._post_cache = {}           # {job_id: post_text} for scrape_job()
```

Requires `llm_api_key` because both `search_jobs()` (classification) and `scrape_job()` (field extraction) use LLM calls. `_post_cache` stores raw post text keyed by job ID since there's no separate job page to navigate to.

## Methods

### login()

1. Navigate to `mbasic.facebook.com`
2. Inject all cookies from JSON file onto `.facebook.com` domain
3. Navigate to `mbasic.facebook.com/me` to validate login
4. Check if page contains profile content (not a login form)
5. Raise `RuntimeError` if login fails

### search_jobs(filters)

1. For each `group_url` in config:
   - Convert to mbasic URL (`www.facebook.com` → `mbasic.facebook.com`)
   - Navigate to group page
   - Parse posts from HTML — mbasic posts are simple `<div>` elements with text content
   - Follow "See more posts" pagination link
   - Stop when `target_posts` reached or `max_pages` exhausted (whichever first)
2. Batch all collected posts → single LLM call to classify which are job posts
3. If `filter_remote_only: true` in config, second LLM call to filter remote-only jobs
4. For each job post:
   - Generate ID: `facebook_{md5(post_content)[:16]}`
   - Cache text in `_post_cache`
   - Return `{id, url: group_url, role: "", company: ""}`

### scrape_job(job_url)

Since Facebook posts don't have a separate detail page:
1. Look up post text from `_post_cache` using job ID
2. Single LLM call to extract: role, company, location, description
3. Return populated `Job` dataclass

## LLM Prompts

**Classify job posts** (batch, all posts in one call):
```
Given the numbered Facebook posts below, identify posts that are clearly
job-related (hiring, recruitment, job opening, looking for candidate, job offer).
Return only a JSON array of integers (1-based indexes), with no extra text.
```

**Filter remote jobs** (optional, if `filter_remote_only: true`):
```
Given the numbered job posts below, identify only jobs that are explicitly remote
(remote/WFH/work from home/any location/fully remote).
Return only a JSON array of integers (1-based indexes), with no extra text.
```

**Extract job fields** (one call per post):
```
Extract structured job information from this Facebook post.
Return JSON with these fields:
- role: job title/position
- company: company name
- location: job location
- description: full job description

If a field cannot be determined, use empty string.
Return only valid JSON, no extra text.
```

## Configuration

Add to `data_folder/crawler_config.yaml`:

```yaml
facebook:
  group_urls:
    - "https://www.facebook.com/groups/123456"
    - "https://www.facebook.com/groups/789012"
  cookies_file: "facebook.com.cookies.json"
  target_posts: 25
  max_pages: 10
  filter_remote_only: false
```

Cookie file: user exports from browser extension (Cookie-Editor, EditThisCookie, etc.), saved as JSON array in `data_folder/facebook.com.cookies.json`.

Add `facebook: dict[str, Any]` field to `CrawlerConfig` dataclass.

## Runner Integration

In `runner.py`, add Facebook crawler to the loop:

```python
if crawler_name == "facebook":
    fb_config = config.facebook
    cookies_path = data_path / fb_config.get("cookies_file", "facebook.com.cookies.json")
    cookies = json.loads(cookies_path.read_text())

    crawler_config = {
        **fb_config,
        "min_delay": config.rate_limiting.get("min_delay", 2),
        "max_delay": config.rate_limiting.get("max_delay", 5),
    }
    crawler = FacebookCrawler(
        crawl_driver, tracker, crawler_config,
        cookies=cookies, llm_api_key=llm_api_key,
    )
    crawler.login()
    jobs = crawler.crawl(fb_config)
    all_jobs.extend(jobs)
```

## m.facebook.com Parsing

mbasic.facebook.com renders pure HTML:
- Posts are in `<div>` elements within the group feed
- Pagination via "See more posts" anchor link at bottom
- No JavaScript rendering needed
- Simpler DOM than main site, more stable selectors
- Less bot detection than www.facebook.com

## Deduplication

- Job ID format: `facebook_{md5(post_content)[:16]}`
- Uses existing `Tracker` for cross-run dedup
- Posts with same content across groups are deduped

## Error Handling

- If LLM classification fails, log error and skip batch
- If LLM field extraction fails for a post, return Job with raw text as description
- If cookie file missing/invalid, log error and skip Facebook crawler
- If group page fails to load, log and continue to next group

## Files

### New
- `src/crawlers/facebook.py` — `FacebookCrawler` class
- `tests/test_facebook_crawler.py` — unit tests

### Modified
- `src/crawlers/config.py` — add `facebook` field to `CrawlerConfig`
- `src/crawlers/runner.py` — register Facebook crawler in loop
- `src/crawlers/__init__.py` — export `FacebookCrawler`
- `data_folder_example/crawler_config.yaml` — add facebook config example

## Scope

### In scope
- `FacebookCrawler` extending `BaseCrawler`
- mbasic.facebook.com parsing + pagination
- LLM classification and field extraction
- Cookie-based authentication from JSON file
- Integration with runner and tracker
- Configurable remote-only filter

### Out of scope
- Facebook Graph API integration
- www.facebook.com scrolling-based crawling
- Facebook Marketplace jobs
- Comment/reply parsing within posts
