import hashlib
import json
import re
import time

from selenium.webdriver.common.by import By

from src.job import Job
from src.logging import logger
from src.crawlers.base import BaseCrawler
from src.crawlers.tracker import Tracker

from langchain_core.messages import HumanMessage


class FacebookCrawler(BaseCrawler):
    """Crawls Facebook group posts via www.facebook.com with scroll-based pagination."""

    BASE_URL = "https://www.facebook.com"

    def __init__(self, driver, tracker: Tracker, config: dict, cookies: list, llm_api_key: str):
        super().__init__(driver, tracker, config)
        self.cookies = cookies
        self.llm_api_key = llm_api_key
        self._post_cache: dict[str, str] = {}

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Ensure URL uses www.facebook.com."""
        return re.sub(r"https://(m\.|mbasic\.)?facebook\.com", "https://www.facebook.com", url)

    @staticmethod
    def _generate_post_id(text: str) -> str:
        return "facebook_" + hashlib.md5(text.encode()).hexdigest()[:16]

    def login(self) -> None:
        logger.info("Logging into Facebook via cookies...")
        self.driver.get(self.BASE_URL)
        time.sleep(2)

        for cookie in self.cookies:
            clean = {k: v for k, v in cookie.items() if k in ("name", "value", "domain", "path", "secure", "httpOnly")}
            if "domain" not in clean:
                clean["domain"] = ".facebook.com"
            try:
                self.driver.add_cookie(clean)
            except Exception as e:
                logger.debug(f"Failed to add cookie {clean.get('name')}: {e}")

        self.driver.get(f"{self.BASE_URL}/me")
        time.sleep(3)

        current_url = self.driver.current_url
        page_source = self.driver.page_source
        if "/login" in current_url or "login_form" in page_source:
            raise RuntimeError(
                "Facebook login failed — cookies may be expired. "
                "Please re-export your Facebook cookies."
            )
        logger.info(f"Facebook login successful (URL: {current_url})")

    def search_jobs(self, filters: dict) -> list[dict]:
        group_urls = self.config.get("group_urls", [])
        target_posts = self.config.get("target_posts", 25)
        max_pages = self.config.get("max_pages", 10)
        filter_remote = self.config.get("filter_remote_only", False)

        all_posts = []
        for group_url in group_urls:
            normalized_url = self._normalize_url(group_url)
            posts = self._crawl_group_posts(normalized_url, target_posts, max_pages)
            all_posts.extend(posts)
            logger.info(f"Crawled {len(posts)} posts from {group_url}")

        if not all_posts:
            return []

        job_posts = self._llm_classify_job_posts(all_posts)
        logger.info(f"LLM classified {len(job_posts)}/{len(all_posts)} posts as job listings")

        if filter_remote and job_posts:
            job_posts = self._llm_filter_remote(job_posts)
            logger.info(f"After remote filter: {len(job_posts)} posts")

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
        job_id = job_url
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
            job = None
            try:
                job = self.scrape_job(result["id"])
                jobs.append(job)
            except Exception as e:
                logger.error(f"Failed to extract job from post: {e}")
            self.tracker.mark_seen(
                result["id"], result["url"],
                role=job.role if job else "",
                company=job.company if job else "",
                location=job.location if job else "",
                description=job.description if job else "",
                source="facebook",
            )
        return jobs

    def _crawl_group_posts(self, group_url: str, target_posts: int, max_scrolls: int) -> list[dict]:
        """Crawl posts from Facebook group via scrolling."""
        posts = []
        seen_texts = set()
        stagnant_rounds = 0

        logger.info(f"Crawling group: {group_url}")
        self.driver.get(group_url)
        time.sleep(5)

        # Click "See more" / "Xem thêm" on posts to expand content
        self._expand_all_posts()

        for scroll in range(max_scrolls):
            # Facebook post content selectors (ordered by reliability)
            post_selectors = [
                'div[data-ad-comet-preview="message"]',
                'div[data-ad-preview="message"]',
                'div.x126k92a',
            ]
            post_elements = []
            for sel in post_selectors:
                post_elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if post_elements:
                    break

            new_on_scroll = 0
            for el in post_elements:
                try:
                    text = el.text.strip()
                    if len(text) < 30 or len(text) > 5000:
                        continue
                    text_key = text[:100]
                    if text_key in seen_texts:
                        continue
                    seen_texts.add(text_key)
                    posts.append({"text": text, "group_url": group_url})
                    new_on_scroll += 1
                except Exception:
                    continue

            logger.info(f"Scroll {scroll + 1}/{max_scrolls}: {new_on_scroll} new, {len(posts)} total")

            if len(posts) >= target_posts:
                break

            if new_on_scroll == 0:
                stagnant_rounds += 1
                if stagnant_rounds >= 3:
                    logger.info("No new posts after 3 scrolls, stopping")
                    break
            else:
                stagnant_rounds = 0

            # Scroll down to load more posts
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)

            # Expand new "See more" links after scroll
            self._expand_all_posts()

        return posts[:target_posts]

    def _expand_all_posts(self):
        """Click all 'See more' / 'Xem thêm' links to expand post content."""
        try:
            see_more_links = self.driver.find_elements(
                By.XPATH,
                "//div[@role='button' and (contains(text(), 'See more') or contains(text(), 'Xem thêm'))]"
            )
            for link in see_more_links[:10]:
                try:
                    link.click()
                    time.sleep(0.3)
                except Exception:
                    continue
        except Exception:
            pass

    def _get_llm(self):
        from src.libs.resume_and_cover_builder.llm.llm_factory import create_llm
        return create_llm(self.llm_api_key)

    def _llm_classify_job_posts(self, posts: list[dict]) -> list[dict]:
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
            match = re.search(r'\[[\d\s,]*\]', content)
            if match:
                indexes = json.loads(match.group())
                return [posts[i - 1] for i in indexes if 1 <= i <= len(posts)]
        except Exception as e:
            logger.error(f"LLM job classification failed: {e}")
        return []

    def _llm_filter_remote(self, posts: list[dict]) -> list[dict]:
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
        return posts

    def _llm_extract_job_fields(self, post_text: str) -> dict:
        prompt = (
            "Extract structured job information from this Facebook post. "
            "Return JSON with these fields:\n"
            "- role: job title/position\n"
            "- company: company name\n"
            "- location: job location\n"
            "- description: full job description\n\n"
            "If a field cannot be determined, use empty string. "
            "Return only valid JSON, no extra text.\n\n"
            f"Post:\n{post_text}"
        )

        try:
            llm = self._get_llm()
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            return json.loads(content)
        except Exception as e:
            logger.error(f"LLM field extraction failed: {e}")
            return {"role": "", "company": "", "location": "", "description": post_text}
