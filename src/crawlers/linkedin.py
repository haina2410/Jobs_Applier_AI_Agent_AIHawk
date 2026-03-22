import time
from urllib.parse import urlencode

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

    JOBS_PER_PAGE = 25

    def __init__(self, driver, tracker: Tracker, config: dict, cookies: dict):
        super().__init__(driver, tracker, config)
        self.cookies = cookies

    def login(self) -> None:
        logger.info("Logging into LinkedIn via cookies...")
        self.driver.get("https://www.linkedin.com")
        time.sleep(2)

        # Inject all provided LinkedIn cookies
        for name, value in self.cookies.items():
            if value:
                self.driver.add_cookie({
                    "name": name,
                    "value": value,
                    "domain": ".linkedin.com",
                })
                logger.debug(f"Injected cookie: {name}")

        self.driver.get("https://www.linkedin.com/feed/")
        time.sleep(3)

        # Check if we're logged in — LinkedIn uses various selectors across versions
        logged_in_selectors = [
            ".feed-identity-module",
            ".global-nav__me",
            ".global-nav__primary-items",
            "[data-control-name='identity_welcome_message']",
            ".scaffold-layout__main",
        ]
        for selector in logged_in_selectors:
            indicators = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if indicators:
                logger.info(f"LinkedIn login successful (matched: {selector})")
                return

        # If no selector matched, check if we're on a logged-in page by URL
        current_url = self.driver.current_url
        if "/feed" in current_url or "/mynetwork" in current_url:
            logger.info(f"LinkedIn login successful (URL: {current_url})")
            return

        # Check if we got redirected to login page
        if "/login" in current_url or "/checkpoint" in current_url:
            raise RuntimeError(
                "LinkedIn login failed — redirected to login/checkpoint page. "
                "Your li_at cookie may be expired. Please refresh it in secrets.yaml."
            )

        # Last resort: check page title
        title = self.driver.title.lower()
        if "linkedin" in title and "login" not in title and "join" not in title:
            logger.info(f"LinkedIn login likely successful (title: {self.driver.title})")
            return

        logger.warning(f"LinkedIn login uncertain — URL: {current_url}, title: {self.driver.title}")
        logger.warning("Proceeding anyway — if crawling fails, refresh your cookies in secrets.yaml.")

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

                    # Role + link from the job card title link
                    title_el = card.find_element(By.CSS_SELECTOR, ".job-card-container__link")
                    role = title_el.text.strip()
                    link = title_el.get_attribute("href")

                    # Company from the subtitle
                    try:
                        company_el = card.find_element(By.CSS_SELECTOR, ".artdeco-entity-lockup__subtitle span")
                        company = company_el.text.strip()
                    except Exception:
                        company = ""

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
        time.sleep(3)

        # Click "show more" on description if present
        try:
            show_more = self.driver.find_element(By.CSS_SELECTOR, ".jobs-description__footer-button, button[aria-label*='more']")
            show_more.click()
            time.sleep(1)
        except Exception:
            pass

        job = Job()
        job.link = job_url

        # Extract from page title (reliable: "Role | Company | LinkedIn")
        title = self.driver.title
        if "|" in title:
            parts = [p.strip() for p in title.split("|")]
            if len(parts) >= 2:
                job.role = parts[0]
                job.company = parts[1] if parts[1].lower() != "linkedin" else ""

        # Try CSS selectors as fallback for role
        if not job.role:
            for sel in ["h1", ".t-24.t-bold", ".jobs-unified-top-card__job-title", ".top-card-layout__title"]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if el.text.strip():
                        job.role = el.text.strip()
                        break
                except Exception:
                    continue

        # Try to extract description from the "About the job" section
        desc_selectors = [
            ".jobs-description__content",
            ".jobs-description-content",
            ".jobs-box__html-content",
            "#job-details",
        ]
        for sel in desc_selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    job.description = el.text.strip()
                    break
            except Exception:
                continue

        # Fallback: extract text between "About the job" and next section
        if not job.description:
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                marker = "About the job"
                if marker in body_text:
                    after = body_text.split(marker, 1)[1]
                    # Cut at known section boundaries
                    for boundary in ["Set alert for similar jobs", "About the company", "People also viewed"]:
                        if boundary in after:
                            after = after.split(boundary, 1)[0]
                    job.description = after.strip()
            except Exception:
                logger.warning("Could not extract job description")

        # Extract location from page text
        if not job.location:
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                # Location usually appears right after company name in the top card
                for line in body_text.split("\n"):
                    line = line.strip()
                    if "·" in line and ("ago" in line.lower() or "people" in line.lower()):
                        # Pattern: "Location · Posted X days ago · N applicants"
                        job.location = line.split("·")[0].strip()
                        break
            except Exception:
                logger.debug("Could not extract location from job page")

        logger.info(f"Scraped: {job.role} at {job.company} ({job.location})")
        return job
