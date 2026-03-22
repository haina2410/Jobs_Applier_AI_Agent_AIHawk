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
        """Template method: search -> dedup -> scrape."""
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
