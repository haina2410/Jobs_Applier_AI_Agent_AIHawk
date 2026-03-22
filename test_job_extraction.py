"""
Standalone script to test job extraction functionality.
This extracts job information from a given URL using LLM and FAISS.
"""
import json
import os
import re
import shutil
import sys
import time
import yaml
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.libs.resume_and_cover_builder.llm.llm_factory import create_llm
from src.libs.resume_and_cover_builder.llm.llm_job_parser import LLMParser
from src.utils.chrome_utils import init_browser
from src.job import Job
from src.logging import logger

DEFAULT_FACEBOOK_COOKIE_FILE = "facebook.com.cookies.json"
DEFAULT_FACEBOOK_GROUP_URLS = [
    "https://www.facebook.com/groups/ithotjobs.tuyendungit.vieclamcntt.susudev/?sorting_setting=CHRONOLOGICAL",
    "https://www.facebook.com/groups/Freelance.Remote.IT.Jobs.VN/?sorting_setting=CHRONOLOGICAL",
    "https://www.facebook.com/groups/5097678227028214/?sorting_setting=CHRONOLOGICAL"
]
DEBUG_STEPS_DIR = project_root / "debug_steps"
REMOTE_POSTS_OUTPUT_JSON = project_root / "facebook_remote_posts.json"
JOB_POSTS_OUTPUT_JSON = project_root / "facebook_job_posts.json"
TARGET_POSTS_COUNT = 25
POST_CONTAINER_CLASS_SUBSTR = "xdj266r x14z9mp xat24cr x1lziwak xexx8yu xyri2b x18d9i69 x1c1uobl"
POST_CONTENT_CLASS_BASE = "xdj266r x14z9mp xat24cr x1lziwak x1vvkbs"
POST_CONTENT_CLASS_EXTENDED = "xdj266r x14z9mp xat24cr x1lziwak x1vvkbs x126k92a"
NOISE_PHRASES = [
    "see everyone",
    "write something",
    "feeling/activity",
    "check in",
    "poll",
    "group by",
    "sort group feed by",
    "public group",
    "members",
    "invite",
    "share",
    "joined",
]


def extract_job_from_url(job_url: str, api_key: str) -> Job:
    """
    Extract job information from a given URL.
    
    Args:
        job_url: The URL of the job posting
        api_key: Your OpenAI/LLM API key
        
    Returns:
        Job object with extracted information
    """
    started_at = time.time()
    logger.info(f"[STD-01] Starting standard job extraction for URL: {job_url}")
    
    # Step 1: Initialize browser
    logger.info("[STD-02] Initializing browser...")
    driver = init_browser()
    
    try:
        # Step 2: Navigate to job URL and get HTML
        logger.info(f"[STD-03] Navigating to target URL: {job_url}")
        driver.get(job_url)
        
        # Wait for page to load
        import time
        logger.info("[STD-04] Waiting for page stabilization (3s)...")
        time.sleep(3)
        
        # Get page HTML
        page_html = driver.page_source
        logger.info(f"[STD-05] Retrieved HTML content size: {len(page_html)} chars")
        
        # Step 3: Initialize LLM Parser
        logger.info("[STD-06] Initializing LLM parser...")
        parser = LLMParser(openai_api_key=api_key)
        
        # Step 4: Load HTML into parser (creates FAISS vectorstore)
        logger.info("[STD-07] Processing HTML and preparing retrieval context...")
        parser.set_body_html(page_html)
        
        # Step 5: Extract job information
        logger.info("[STD-08] Starting structured field extraction...")
        
        job = Job()
        job.link = job_url
        
        # Extract each field
        logger.info("[STD-09] Extracting company name...")
        job.company = parser.extract_company_name()
        logger.info(f"[STD-09] Company extracted: {job.company}")
        
        logger.info("[STD-10] Extracting job role/title...")
        job.role = parser.extract_role()
        logger.info(f"[STD-10] Role extracted: {job.role}")
        
        logger.info("[STD-11] Extracting location...")
        job.location = parser.extract_location()
        logger.info(f"[STD-11] Location extracted: {job.location}")
        
        logger.info("[STD-12] Extracting job description...")
        job.description = parser.extract_job_description()
        logger.info(f"[STD-12] Description length: {len(job.description or '')} chars")
        
        logger.info("[STD-13] Extracting recruiter email...")
        recruiter_email = parser.extract_recruiter_email()
        job.recruiter_link = recruiter_email if recruiter_email else "Not found"
        logger.info(f"[STD-13] Recruiter email extracted: {job.recruiter_link}")
        
        logger.info(f"[STD-14] Standard extraction completed in {time.time() - started_at:.2f}s")
        return job
        
    except Exception as e:
        logger.error(f"[STD-ERR] Error during standard job extraction: {e}")
        raise
    finally:
        # Clean up browser
        logger.info("[STD-15] Closing browser...")
        driver.quit()


def reset_debug_steps_dir():
    logger.info(f"[DBG-01] Resetting debug directory: {DEBUG_STEPS_DIR}")
    if DEBUG_STEPS_DIR.exists():
        for item in DEBUG_STEPS_DIR.iterdir():
            if item.is_file() or item.is_symlink():
                item.unlink(missing_ok=True)
            elif item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
    DEBUG_STEPS_DIR.mkdir(parents=True, exist_ok=True)


def _debug_target_path(filename: str, debug_prefix: str = "") -> Path:
    final_name = f"{debug_prefix}__{filename}" if debug_prefix else filename
    return DEBUG_STEPS_DIR / final_name


def write_debug_json(filename: str, payload, debug_prefix: str = ""):
    target = _debug_target_path(filename, debug_prefix)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"[DBG] Wrote JSON debug file: {target}")


def write_debug_html(filename: str, html: str, debug_prefix: str = ""):
    target = _debug_target_path(filename, debug_prefix)
    with open(target, "w", encoding="utf-8") as f:
        f.write(html or "")
    logger.info(f"[DBG] Wrote HTML debug file: {target}")


def make_debug_prefix(group_url: str, idx: int) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", group_url).strip("_").lower()
    return f"url{idx:02d}_{slug[:50]}"


def _safe_text(element, xpath: str) -> str:
    try:
        return element.find_element(By.XPATH, xpath).text.strip()
    except Exception:
        return ""


def _safe_attr(element, xpath: str, attr: str) -> str:
    try:
        found = element.find_element(By.XPATH, xpath)
        return (found.get_attribute(attr) or "").strip()
    except Exception:
        return ""


def _extract_facebook_post(article) -> Optional[Dict[str, str]]:
    try:
        author = _safe_text(
            article,
            ".//h2//a | .//h3//a | .//strong//a | .//span[contains(@class,'html-span')]//a",
        )

        time_label = _safe_attr(
            article,
            ".//a[@aria-label and (contains(@href,'/posts/') or contains(@href,'/permalink/') or contains(@href,'story_fbid') or contains(@href,'multi_permalinks'))]",
            "aria-label",
        )
        if not time_label:
            time_label = "Unknown"

        content_candidates: List[str] = []

        # Rule 1: exact base class; only accept pure-text nodes (no nested elements).
        base_nodes = article.find_elements(By.XPATH, f".//div[@class='{POST_CONTENT_CLASS_BASE}']")
        for node in base_nodes:
            has_child_elements = len(node.find_elements(By.XPATH, ".//*")) > 0
            if has_child_elements:
                continue
            text_content = (node.get_attribute("textContent") or "").strip()
            if text_content:
                content_candidates.append(text_content)

        # Rule 2: exact extended class with x126k92a; accept text content.
        extended_nodes = article.find_elements(By.XPATH, f".//div[@class='{POST_CONTENT_CLASS_EXTENDED}']")
        for node in extended_nodes:
            text_content = (node.get_attribute("textContent") or "").strip()
            if text_content:
                content_candidates.append(text_content)
    except StaleElementReferenceException:
        logger.debug("[FB-POST] Stale element in _extract_facebook_post; skipping this node.")
        return None

    if content_candidates:
        content = max(content_candidates, key=len, default="")
    else:
        content = ""
    if not content:
        logger.debug("[FB-POST] Skipping article: no content extracted.")
        return None
    content = re.sub(r"\s+", " ", content).strip()
    if len(content) < 30:
        logger.debug("[FB-POST] Skipping article: content too short.")
        return None
    post = {
        "author": author or "Unknown",
        "time_label": time_label or "Unknown",
        "content": content[:2500],
    }
    logger.debug(
        f"[FB-POST] Extracted post | author={post['author']} | time={post['time_label']} | "
        f"content_len={len(post['content'])}"
    )
    return post


def _is_noise_post(post: Dict[str, str]) -> bool:
    author = (post.get("author") or "").strip().lower()
    content = (post.get("content") or "").strip().lower()

    content_compact = re.sub(r"\s+", " ", content)
    if not content_compact or len(content_compact) < 30:
        return True

    if content_compact == author:
        return True

    for phrase in NOISE_PHRASES:
        if phrase in content_compact:
            return True

    return False


def apply_facebook_cookies(driver, cookie_file_path: str, debug_prefix: str = ""):
    logger.info(f"[FB-01] Loading cookies from: {cookie_file_path}")
    with open(cookie_file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    cookies = raw.get("cookies", []) if isinstance(raw, dict) else raw
    if not isinstance(cookies, list):
        raise ValueError("Cookie file must be a JSON list or object with 'cookies' list.")
    logger.info(f"[FB-02] Parsed cookie entries: {len(cookies)}")

    logger.info("[FB-03] Opening facebook.com before cookie injection...")
    driver.get("https://www.facebook.com/")
    time.sleep(2)

    added_count = 0
    skipped_count = 0
    for cookie in cookies:
        if not isinstance(cookie, dict):
            skipped_count += 1
            continue
        c = dict(cookie)
        if "expirationDate" in c and "expiry" not in c:
            c["expiry"] = int(c["expirationDate"])

        allowed = {"name", "value", "domain", "path", "expiry", "secure", "httpOnly", "sameSite"}
        cleaned = {k: v for k, v in c.items() if k in allowed}
        same_site = cleaned.get("sameSite")
        if same_site not in (None, "Strict", "Lax", "None"):
            cleaned.pop("sameSite", None)
        if "name" in cleaned and "value" in cleaned:
            try:
                driver.add_cookie(cleaned)
                added_count += 1
            except Exception as e:
                skipped_count += 1
                logger.debug(f"Skipping cookie {cleaned.get('name')}: {e}")
        else:
            skipped_count += 1

    logger.info(f"[FB-04] Cookie injection done. Added={added_count}, skipped={skipped_count}")

    logger.info("[FB-05] Refreshing facebook.com after cookie injection...")
    driver.get("https://www.facebook.com/")
    time.sleep(3)
    logger.info(f"[FB-06] Post-cookie URL: {driver.current_url}")
    write_debug_json(
        "step_01_cookie_apply_result.json",
        {
            "post_cookie_url": driver.current_url,
            "cookies_added": added_count,
            "cookies_skipped": skipped_count,
        },
        debug_prefix=debug_prefix,
    )
    write_debug_html("step_01_after_cookie_login.html", driver.page_source, debug_prefix=debug_prefix)


def crawl_latest_facebook_posts(
    driver,
    group_url: str,
    target_posts: int = TARGET_POSTS_COUNT,
    max_scrolls: int = 25,
    debug_prefix: str = "",
) -> List[Dict[str, str]]:
    logger.info(f"[FB-07] Navigating to group URL: {group_url}")
    driver.get(group_url)
    logger.info("[FB-08] Waiting for feed container...")
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                f"//div[contains(@class,'html-div') and contains(@class,'{POST_CONTAINER_CLASS_SUBSTR}')]",
            )
        )
    )
    time.sleep(2)
    logger.info("[FB-09] Feed detected. Starting crawl loop...")
    write_debug_html("step_02_group_loaded.html", driver.page_source, debug_prefix=debug_prefix)

    posts: List[Dict[str, str]] = []
    seen_content = set()
    stagnant_rounds = 0
    accepted_meta: List[Dict[str, object]] = []

    def _find_content_nodes():
        return driver.find_elements(
            By.XPATH,
            f"//div[@class='{POST_CONTENT_CLASS_BASE}' or @class='{POST_CONTENT_CLASS_EXTENDED}']",
        )

    def _count_post_containers() -> int:
        return len(
            driver.find_elements(
                By.XPATH,
                f"//div[@class='{POST_CONTENT_CLASS_BASE}' or @class='{POST_CONTENT_CLASS_EXTENDED}']",
            )
        )

    def _continuous_scroll_until_growth(max_attempts: int = 8, step_px: int = 1400) -> Dict[str, object]:
        """
        Scroll repeatedly until either page height or container count grows.
        Returns debug stats of the cycle.
        """
        initial_height = driver.execute_script("return document.body.scrollHeight")
        initial_count = _count_post_containers()
        growth_detected = False
        attempts_used = 0

        for attempt in range(max_attempts):
            attempts_used = attempt + 1
            driver.execute_script(f"window.scrollBy(0, {step_px});")
            time.sleep(0.6)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.9)

            current_height = driver.execute_script("return document.body.scrollHeight")
            current_count = _count_post_containers()
            if current_height > initial_height or current_count > initial_count:
                growth_detected = True
                break

        final_height = driver.execute_script("return document.body.scrollHeight")
        final_count = _count_post_containers()
        return {
            "initial_height": initial_height,
            "final_height": final_height,
            "initial_count": initial_count,
            "final_count": final_count,
            "growth_detected": growth_detected,
            "attempts_used": attempts_used,
        }

    for scroll_idx in range(max_scrolls):
        logger.info(f"[FB-10] Scroll cycle {scroll_idx + 1}/{max_scrolls}")
        scroll_stats = _continuous_scroll_until_growth(max_attempts=8, step_px=1400)
        prev_height = scroll_stats["initial_height"]

        content_nodes = _find_content_nodes()
        logger.info(f"[FB-11] Found {len(content_nodes)} matching content nodes")

        # Debug: dump all crawled container HTML blocks for this scroll cycle.
        container_blocks: List[str] = []
        stale_container_html = 0
        for node_idx, node in enumerate(content_nodes, 1):
            try:
                raw_html = node.get_attribute("outerHTML") or ""
                container_blocks.append(
                    f"\n<!-- scroll={scroll_idx + 1}, content_node={node_idx} -->\n{raw_html}\n"
                )
            except StaleElementReferenceException:
                stale_container_html += 1
                continue
        write_debug_html(
            f"step_03_scroll_{scroll_idx + 1}_containers.html",
            "<html><body>\n" + "\n<hr/>\n".join(container_blocks) + "\n</body></html>",
            debug_prefix=debug_prefix,
        )

        before_count = len(posts)
        skipped_empty = 0
        skipped_duplicate = 0
        skipped_noise = 0
        skipped_no_article = 0
        skipped_invalid_class = 0
        skipped_stale = 0
        for node_idx, node in enumerate(content_nodes, 1):
            try:
                node_class = (node.get_attribute("class") or "").strip()
                is_base = node_class == POST_CONTENT_CLASS_BASE
                is_extended = node_class == POST_CONTENT_CLASS_EXTENDED
                if not (is_base or is_extended):
                    skipped_invalid_class += 1
                    continue

                # Base class must be pure text (no child elements).
                if is_base:
                    if len(node.find_elements(By.XPATH, ".//*")) > 0:
                        skipped_invalid_class += 1
                        continue

                raw_text = (node.get_attribute("textContent") or "").strip()
                normalized_content = re.sub(r"\s+", " ", raw_text).strip()
                if not normalized_content:
                    skipped_empty += 1
                    continue

                parent_articles = node.find_elements(By.XPATH, "./ancestor::div[@role='article'][1]")
            except StaleElementReferenceException:
                skipped_stale += 1
                continue

            author = "Unknown"
            time_label = "Unknown"
            article = None
            if parent_articles:
                article = parent_articles[0]
                post = _extract_facebook_post(article)
                if post:
                    author = post.get("author", "Unknown")
                    time_label = post.get("time_label", "Unknown")
            else:
                skipped_no_article += 1

            post = {
                "author": author,
                "time_label": time_label,
                "content": normalized_content[:2500],
            }
            if _is_noise_post(post):
                skipped_noise += 1
                continue
            content_key = re.sub(r"\s+", " ", post["content"]).strip().lower()[:600]
            if not content_key or content_key in seen_content:
                skipped_duplicate += 1
                continue
            seen_content.add(content_key)
            posts.append(post)
            accepted_no = len(posts)
            try:
                accepted_html = (article.get_attribute("outerHTML") if article else node.get_attribute("outerHTML")) or ""
            except StaleElementReferenceException:
                skipped_stale += 1
                accepted_html = ""
            write_debug_html(
                f"step_03_selected_post_{accepted_no:02d}.html",
                accepted_html,
                debug_prefix=debug_prefix,
            )
            accepted_meta.append(
                {
                    "accepted_no": accepted_no,
                    "scroll_cycle": scroll_idx + 1,
                    "content_node_index": node_idx,
                    "author": post.get("author"),
                    "time_label": post.get("time_label"),
                    "content_preview": (post.get("content") or "")[:180],
                }
            )
            if len(posts) >= target_posts:
                logger.info(f"[FB-12] Reached target post count: {target_posts}")
                break

        added_now = len(posts) - before_count
        logger.info(f"[FB-12] New unique posts this cycle: {added_now} | Total: {len(posts)}")
        new_height = scroll_stats["final_height"]
        height_changed = new_height > prev_height

        if added_now == 0 and not height_changed:
            stagnant_rounds += 1
            logger.info(f"[FB-13] No new posts and no page growth. Stagnant rounds: {stagnant_rounds}")
            # Recovery nudges for dynamic feed loading
            driver.execute_script("window.scrollBy(0, -600);")
            time.sleep(0.8)
            driver.execute_script("window.scrollBy(0, 2200);")
            time.sleep(1.2)
        else:
            stagnant_rounds = 0

        write_debug_json(
            f"step_03_scroll_{scroll_idx + 1}.json",
            {
                "scroll_cycle": scroll_idx + 1,
                "found_containers": len(content_nodes),
                "added_now": added_now,
                "skipped_empty": skipped_empty,
                "skipped_duplicate": skipped_duplicate,
                "skipped_noise": skipped_noise,
                "skipped_no_article": skipped_no_article,
                "skipped_invalid_class": skipped_invalid_class,
                "skipped_stale": skipped_stale,
                "stale_container_html": stale_container_html,
                "total_collected": len(posts),
                "prev_height": prev_height,
                "new_height": new_height,
                "height_changed": height_changed,
                "scroll_growth_detected": scroll_stats["growth_detected"],
                "scroll_attempts_used": scroll_stats["attempts_used"],
                "container_count_before": scroll_stats["initial_count"],
                "container_count_after": scroll_stats["final_count"],
                "stagnant_rounds": stagnant_rounds,
                "sample_preview": [p["content"][:150] for p in posts[: min(3, len(posts))]],
            },
            debug_prefix=debug_prefix,
        )
        if len(posts) >= target_posts:
            break
        if stagnant_rounds >= 5:
            logger.info("[FB-14] Feed appears exhausted after repeated stagnation, stopping early.")
            break

    final_posts = posts[:target_posts]
    write_debug_json(
        f"step_04_collected_latest_{target_posts}_posts.json",
        final_posts,
        debug_prefix=debug_prefix,
    )
    write_debug_json(
        "step_04_selected_posts_meta.json",
        accepted_meta[:target_posts],
        debug_prefix=debug_prefix,
    )
    logger.info(f"[FB-15] Crawl completed. Total latest posts collected: {len(final_posts)}")
    return final_posts


def _extract_json_array_from_text(text: str) -> List[int]:
    if not text:
        return []
    match = re.search(r"\[[\s\S]*?\]", text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
        if isinstance(data, list):
            return [int(x) for x in data if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit())]
    except Exception:
        return []
    return []


def classify_job_posts_with_llm(
    posts: List[Dict[str, str]],
    api_key: str,
    debug_prefix: str = "",
    source_url: str = "",
) -> List[Dict[str, str]]:
    if not posts:
        logger.info("[FB-JOB] No posts to classify.")
        return []

    llm = create_llm(api_key)
    prompt_lines = []
    for idx, post in enumerate(posts, 1):
        prompt_lines.append(
            f"{idx}. Author: {post.get('author', 'Unknown')}\n"
            f"   Time: {post.get('time_label', 'Unknown')}\n"
            f"   Text: {post.get('content', '')}"
        )
    payload = "\n\n".join(prompt_lines)
    write_debug_json(
        "step_05_job_filter_input_posts.json",
        {
            "post_count": len(posts),
            "posts": posts,
            "payload_preview": payload[:12000],
        },
        debug_prefix=debug_prefix,
    )

    prompt = (
        "Given the numbered Facebook posts below, identify posts that are clearly job-related "
        "(hiring, recruitment, job opening, looking for candidate, job offer). "
        "Return only a JSON array of integers (1-based indexes), with no extra text.\n\n"
        f"{payload}"
    )
    write_debug_json(
        "step_05_job_filter_input_prompt.json",
        {
            "prompt_length": len(prompt),
            "prompt": prompt,
        },
        debug_prefix=debug_prefix,
    )
    logger.info("[FB-JOB-01] Invoking LLM to classify job-related posts...")
    logger.info(f"[FB-JOB-01] Input posts count: {len(posts)}")
    logger.info(f"[FB-JOB-01] Prompt length: {len(prompt)} chars")
    result = llm.invoke(prompt)
    raw = (result.content if hasattr(result, "content") else str(result)).strip()
    write_debug_json("step_05_job_filter_raw_response.json", {"raw_response": raw}, debug_prefix=debug_prefix)
    logger.info(f"[FB-JOB-02] Raw LLM output: {raw}")
    indexes = _extract_json_array_from_text(raw)
    logger.info(f"[FB-JOB-02] LLM returned job indexes: {indexes}")

    job_posts = []
    for idx in indexes:
        if 1 <= idx <= len(posts):
            src = posts[idx - 1]
            job_posts.append(
                {
                    "author": src.get("author", "Unknown"),
                    "time_label": src.get("time_label", "Unknown"),
                    "JD": src.get("content", ""),
                    "source_url": source_url,
                }
            )
    logger.info(f"[FB-JOB-03] Job posts selected: {len(job_posts)}")
    return job_posts


def filter_remote_jobs_with_llm(
    job_posts: List[Dict[str, str]],
    api_key: str,
    debug_prefix: str = "",
) -> List[Dict[str, str]]:
    if not job_posts:
        logger.info("[FB-REMOTE] No job posts to filter.")
        return []

    llm = create_llm(api_key)
    prompt_lines = []
    for idx, post in enumerate(job_posts, 1):
        prompt_lines.append(
            f"{idx}. Author: {post.get('author', 'Unknown')}\n"
            f"   JD: {post.get('JD', '')}"
        )
    payload = "\n\n".join(prompt_lines)

    prompt = (
        "Given the numbered job posts below, identify only jobs that are explicitly remote "
        "(remote/WFH/work from home/any location/fully remote). "
        "Return only a JSON array of integers (1-based indexes), with no extra text.\n\n"
        f"{payload}"
    )
    logger.info("[FB-REMOTE-01] Invoking LLM to filter remote jobs...")
    result = llm.invoke(prompt)
    raw = (result.content if hasattr(result, "content") else str(result)).strip()
    write_debug_json(
        "step_06_remote_filter_raw_response.json",
        {"raw_response": raw},
        debug_prefix=debug_prefix,
    )
    indexes = _extract_json_array_from_text(raw)
    logger.info(f"[FB-REMOTE-02] LLM returned remote indexes: {indexes}")

    remote_jobs = []
    for idx in indexes:
        if 1 <= idx <= len(job_posts):
            remote_jobs.append(job_posts[idx - 1])
    logger.info(f"[FB-REMOTE-03] Remote jobs selected: {len(remote_jobs)}")
    return remote_jobs


def summarize_posts_with_llm(posts: List[Dict[str, str]], api_key: str) -> str:
    if not posts:
        logger.info("[FB-SUM] No posts provided for summarization.")
        return "No posts collected."

    logger.info(f"[FB-SUM-01] Initializing LLM for summarization. Post count: {len(posts)}")
    llm = create_llm(api_key)
    lines = []
    for idx, p in enumerate(posts, 1):
        lines.append(
            f"Post {idx}\n"
            f"- Author: {p['author']}\n"
            f"- Posted: {p['time_label']}\n"
            f"- Content: {p['content']}\n"
        )
    joined_posts = "\n".join(lines)
    logger.info(f"[FB-SUM-02] Built summarization payload size: {len(joined_posts)} chars")
    prompt = (
        "You are analyzing Facebook group job posts.\n"
        "Summarize in concise bullet points:\n"
        "1) Key hiring roles/skills mentioned\n"
        "2) Companies or recruiters (if any)\n"
        "3) Urgent/important opportunities\n"
        "4) Short action list for the user\n\n"
        f"Posts:\n{joined_posts}"
    )
    logger.info("[FB-SUM-03] Invoking LLM summarization...")
    result = llm.invoke(prompt)
    summary = (result.content if hasattr(result, "content") else str(result)).strip()
    logger.info(f"[FB-SUM-04] Summarization completed. Summary length: {len(summary)} chars")
    return summary


def load_llm_api_key() -> str:
    """
    Load LLM API key for GLM/FPT flow.
    Priority:
    1) LLM_API_KEY env var
    2) data_folder\\secrets.yaml -> llm_api_key
    """
    env_key = os.getenv("LLM_API_KEY")
    if env_key:
        logger.info("[CFG-01] Loaded API key from env var LLM_API_KEY")
        return env_key.strip()

    secrets_path = project_root / "data_folder" / "secrets.yaml"
    if secrets_path.exists():
        logger.info(f"[CFG-02] Looking for API key in {secrets_path}")
        with open(secrets_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        file_key = (data.get("llm_api_key") or "").strip()
        if file_key:
            logger.info("[CFG-03] Loaded API key from data_folder\\secrets.yaml")
            return file_key

    logger.warning("[CFG-ERR] API key not found in env or secrets file.")
    return ""


def main():
    """Main function to run the job extraction test."""
    
    run_started_at = time.time()
    logger.info("[MAIN-01] Script started.")
    print("\n" + "="*70)
    print("         JOB EXTRACTION TEST - Standalone Mode")
    print("="*70 + "\n")
    
    # API key configuration for GLM/FPT:
    # 1) LLM_API_KEY env var
    # 2) data_folder\\secrets.yaml with llm_api_key
    api_key = load_llm_api_key()

    if not api_key:
        print("⚠️  ERROR: Please set your API key!")
        print("\nOptions:")
        print("  1. Set environment variable: LLM_API_KEY='your-key'")
        print("  2. Or create data_folder\\secrets.yaml with: llm_api_key: 'your-key'")
        return
    
    reset_debug_steps_dir()

    # Facebook extraction runs with configurable URL list.
    logger.info("[MAIN-02] Using configured Facebook group URL list and cookie file.")
    group_urls = [u.strip() for u in DEFAULT_FACEBOOK_GROUP_URLS if u.strip()]
    if not group_urls:
        print("❌ No Facebook URLs configured.")
        logger.warning("[MAIN-ERR] DEFAULT_FACEBOOK_GROUP_URLS is empty.")
        return
    cookie_file = str((project_root / DEFAULT_FACEBOOK_COOKIE_FILE).resolve())
    logger.info(f"[MAIN-03] Facebook group URL count: {len(group_urls)}")
    logger.info(f"[MAIN-04] Cookie file path: {cookie_file}")
    print(f"\n🔍 Starting extraction for {len(group_urls)} facebook URLs\n")
    
    try:
        if not Path(cookie_file).exists():
            print(f"❌ Cookie file not found: {cookie_file}")
            logger.warning(f"[MAIN-ERR] Cookie file path not found: {cookie_file}")
            return

        all_crawled_posts: List[Dict[str, str]] = []
        all_job_posts: List[Dict[str, str]] = []
        all_remote_posts: List[Dict[str, str]] = []

        for idx, job_url in enumerate(group_urls, 1):
            debug_prefix = make_debug_prefix(job_url, idx)
            logger.info(f"[MAIN-05] Processing URL {idx}/{len(group_urls)}: {job_url}")

            driver = init_browser()
            try:
                logger.info("[MAIN-06] Applying Facebook cookies...")
                apply_facebook_cookies(driver, cookie_file, debug_prefix=debug_prefix)
                logger.info(f"[MAIN-07] Crawling latest {TARGET_POSTS_COUNT} Facebook posts while scrolling...")
                posts = crawl_latest_facebook_posts(
                    driver,
                    job_url,
                    target_posts=TARGET_POSTS_COUNT,
                    max_scrolls=40,
                    debug_prefix=debug_prefix,
                )
            finally:
                logger.info("[MAIN-08] Closing Facebook crawler browser...")
                driver.quit()

            for p in posts:
                p["source_url"] = job_url
            all_crawled_posts.extend(posts)

            logger.info("[MAIN-10] Classifying job-related posts using AI...")
            job_posts = classify_job_posts_with_llm(
                posts,
                api_key,
                debug_prefix=debug_prefix,
                source_url=job_url,
            )
            write_debug_json("step_05_job_posts.json", job_posts, debug_prefix=debug_prefix)
            all_job_posts.extend(job_posts)

            logger.info("[MAIN-12] Filtering remote jobs using AI...")
            remote_posts = filter_remote_jobs_with_llm(
                job_posts,
                api_key,
                debug_prefix=debug_prefix,
            )
            write_debug_json("step_06_remote_posts.json", remote_posts, debug_prefix=debug_prefix)
            all_remote_posts.extend(remote_posts)

        def _dedupe_by_jd(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
            seen = set()
            out = []
            for item in items:
                jd = re.sub(r"\s+", " ", (item.get("JD") or item.get("content") or "")).strip().lower()
                key = jd[:800]
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(item)
            return out

        merged_job_posts = _dedupe_by_jd(all_job_posts)
        merged_remote_posts = _dedupe_by_jd(all_remote_posts)

        write_debug_json(
            "step_07_merged_summary.json",
            {
                "url_count": len(group_urls),
                "crawled_posts_total": len(all_crawled_posts),
                "job_posts_total_before_dedupe": len(all_job_posts),
                "remote_posts_total_before_dedupe": len(all_remote_posts),
                "job_posts_total_after_dedupe": len(merged_job_posts),
                "remote_posts_total_after_dedupe": len(merged_remote_posts),
            },
        )
        write_debug_json("step_07_merged_job_posts.json", merged_job_posts)
        write_debug_json("step_07_merged_remote_posts.json", merged_remote_posts)

        with open(JOB_POSTS_OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(merged_job_posts, f, ensure_ascii=False, indent=2)
        logger.info(f"[MAIN-11] Job posts JSON output: {JOB_POSTS_OUTPUT_JSON}")

        with open(REMOTE_POSTS_OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(merged_remote_posts, f, ensure_ascii=False, indent=2)
        logger.info(f"[MAIN-13] Remote posts JSON output: {REMOTE_POSTS_OUTPUT_JSON}")

        print("\n" + "=" * 70)
        print(f"Job posts saved: {len(merged_job_posts)}")
        print(f"Job posts JSON: {JOB_POSTS_OUTPUT_JSON}")
        print(f"Remote job posts saved: {len(merged_remote_posts)}")
        print(f"Output JSON: {REMOTE_POSTS_OUTPUT_JSON}")
        print("=" * 70 + "\n")
        logger.info(f"[MAIN-14] Facebook mode completed in {time.time() - run_started_at:.2f}s")
        return
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.exception(f"[MAIN-ERR] Full error trace: {e}")


if __name__ == "__main__":
    main()
