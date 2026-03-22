import base64
import json
import tempfile
from pathlib import Path

import undetected_chromedriver as uc
import yaml

from src.logging import logger
from src.libs.resume_and_cover_builder import ResumeFacade, ResumeGenerator, StyleManager
from src.resume_schemas.resume import Resume
from src.utils.chrome_utils import init_browser
from src.crawlers.config import CrawlerConfig
from src.crawlers.tracker import Tracker
from src.crawlers.linkedin import LinkedInCrawler
from src.crawlers.facebook import FacebookCrawler


def init_crawler_browser(headless: bool = True) -> uc.Chrome:
    """Init undetected-chromedriver for crawling (avoids bot detection)."""
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1200,800")
    options.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
    try:
        driver = uc.Chrome(options=options, headless=headless)
        logger.debug("Undetected Chrome browser initialized for crawling.")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize crawler browser: {e}")
        raise RuntimeError(f"Failed to initialize crawler browser: {e}")


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

    # Init crawl driver (undetected-chromedriver to avoid LinkedIn bot detection)
    crawl_driver = init_crawler_browser()

    all_jobs = []
    try:
        for crawler_name in config.enabled_crawlers:
            if crawler_name == "linkedin":
                li_cookies = secrets.get("linkedin_cookies", {})
                if not li_cookies.get("li_at"):
                    logger.error("Missing linkedin_cookies.li_at in secrets.yaml, skipping LinkedIn")
                    continue

                crawler_config = {
                    **config.linkedin,
                    "min_delay": config.rate_limiting.get("min_delay", 2),
                    "max_delay": config.rate_limiting.get("max_delay", 5),
                }
                crawler = LinkedInCrawler(crawl_driver, tracker, crawler_config, cookies=li_cookies)

                try:
                    crawler.login()
                    jobs = crawler.crawl(config.linkedin.get("filters", {}))
                    all_jobs.extend(jobs)
                    logger.info(f"LinkedIn: found {len(jobs)} new jobs")
                except Exception as e:
                    logger.error(f"LinkedIn crawler failed: {e}")
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
