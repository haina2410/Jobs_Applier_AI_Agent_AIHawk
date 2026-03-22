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

        try:
            role_el = self.driver.find_element(By.CSS_SELECTOR, ".jobs-unified-top-card__job-title, .top-card-layout__title")
            job.role = role_el.text.strip()
        except Exception:
            logger.debug("Could not extract role from job page")

        try:
            company_el = self.driver.find_element(By.CSS_SELECTOR, ".jobs-unified-top-card__company-name, .topcard__org-name-link")
            job.company = company_el.text.strip()
        except Exception:
            logger.debug("Could not extract company from job page")

        try:
            location_el = self.driver.find_element(By.CSS_SELECTOR, ".jobs-unified-top-card__bullet, .topcard__flavor--bullet")
            job.location = location_el.text.strip()
        except Exception:
            logger.debug("Could not extract location from job page")

        try:
            desc_el = self.driver.find_element(By.CSS_SELECTOR, ".jobs-description__content, .jobs-description-content")
            job.description = desc_el.text.strip()
        except Exception:
            logger.warning("Could not extract job description")

        return job
