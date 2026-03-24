"""
process_jobs.py

Filter crawled jobs by per-person keyword rules and use Gemini to produce
tailored CVs. Config is read from config_persons.yaml.

Usage:
    python process_jobs.py [--config PATH] [--person FOLDER] [--dry-run]
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR
CRAWLED_DIR = DATA_DIR / "crawled_jobs"
DEFAULT_CONFIG = BASE_DIR / "config_persons.yaml"

GEMINI_MODEL = "gemini-2.5-flash"
CV_SUBDIR = "cv"           # subfolder inside each person dir holding CV.tex & cv_prompt.txt
CV_FILENAME = "CV.tex"
PROMPT_FILENAME = "cv_prompt.txt"

# Delimiters used to split Gemini's response into CV latex and change log.
# Using plain text markers avoids JSON backslash-escape issues with LaTeX.
_CV_START = "===CV_START==="
_CV_END = "===CV_END==="
_CHANGES_START = "===CHANGES_START==="
_CHANGES_END = "===CHANGES_END==="

# ---------------------------------------------------------------------------
# Job loaders
# ---------------------------------------------------------------------------

def _facebook_id(entry: dict) -> str:
    content = entry.get("JD", "") + entry.get("source_url", "")
    return "facebook_" + hashlib.md5(content.encode()).hexdigest()[:12]


def load_facebook_jobs(filepath: Path) -> list[dict]:
    with open(filepath, encoding="utf-8") as f:
        raw = json.load(f)
    jobs = []
    for entry in raw:
        jd = entry.get("JD", "").strip()
        if not jd:
            continue
        title = jd.split("\n")[0].strip()[:100] or "Untitled"
        jobs.append({
            "job_source_id": _facebook_id(entry),
            "source": "facebook",
            "title": title,
            "company": entry.get("author", "Unknown"),
            "location": "",
            "description": jd,
            "url": entry.get("source_url", ""),
            "crawled_at": "",
        })
    return jobs


def load_linkedin_jobs(filepath: Path) -> list[dict]:
    with open(filepath, encoding="utf-8") as f:
        raw = json.load(f)
    return [
        {
            "job_source_id": key,
            "source": "linkedin",
            "title": entry.get("role", ""),
            "company": entry.get("company", ""),
            "location": entry.get("location", ""),
            "description": entry.get("description", ""),
            "url": entry.get("url", ""),
            "crawled_at": entry.get("crawled_at", ""),
        }
        for key, entry in raw.items()
    ]


def load_all_jobs() -> list[dict]:
    jobs: list[dict] = []
    
    fb_path = CRAWLED_DIR / "facebook" / "facebook_crawled_jobs.json"
    if fb_path.exists():
        jobs.extend(load_facebook_jobs(fb_path))
        
    li_path = CRAWLED_DIR / "linkedin" / "linkedin_crawled_jobs.json"
    if li_path.exists():
        jobs.extend(load_linkedin_jobs(li_path))
        
    return jobs

# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------

def matches_keywords(job: dict, keyword_groups: list[str]) -> bool:
    """All groups must match (AND). Within a group, use | for OR."""
    text = job.get("title", "") + " " + job.get("description", "")
    return all(re.search(p, text, re.IGNORECASE) for p in keyword_groups)

# ---------------------------------------------------------------------------
# Job folder management
# ---------------------------------------------------------------------------

def existing_job_ids(jobs_dir: Path) -> set[str]:
    ids = set()
    if not jobs_dir.exists():
        return ids
    for folder in jobs_dir.iterdir():
        meta = folder / "job.json"
        if meta.exists():
            try:
                ids.add(json.loads(meta.read_text(encoding="utf-8")).get("job_source_id", ""))
            except (json.JSONDecodeError, KeyError):
                pass
    return ids


def next_job_number(jobs_dir: Path) -> int:
    if not jobs_dir.exists():
        return 1
    nums = []
    for folder in jobs_dir.iterdir():
        if folder.is_dir() and folder.name.startswith("job_"):
            try:
                nums.append(int(folder.name.split("_", 1)[1]))
            except (ValueError, IndexError):
                pass
    return max(nums, default=0) + 1

# ---------------------------------------------------------------------------
# Gemini CV customization
# ---------------------------------------------------------------------------

def _extract(text: str, start: str, end: str) -> str:
    try:
        s = text.index(start) + len(start)
        e = text.index(end, s)
        return text[s:e].strip()
    except ValueError:
        return ""


def customize_cv(cv_tex: str, job_desc: str, api_key: str, system_prompt: str) -> tuple[str, str]:
    """Return (cv_latex, changes_markdown) tailored to the job description."""
    try:
        from google import genai
    except ImportError:
        print("ERROR: google-genai not installed. Run: pip install google-genai")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    user_prompt = (
        "## Original CV (LaTeX):\n\n"
        f"{cv_tex}\n\n"
        "## Job Description:\n\n"
        f"{job_desc}\n\n"
        "## Task:\n"
        "Produce the tailored CV and a changes log.\n"
        "Output EXACTLY in this format, no extra text outside the markers:\n\n"
        f"{_CV_START}\n"
        "<full tailored LaTeX here, starting with \\documentclass>\n"
        f"{_CV_END}\n"
        f"{_CHANGES_START}\n"
        "<changes log in markdown here>\n"
        f"{_CHANGES_END}\n"
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_prompt,
        config={"system_instruction": system_prompt, "temperature": 0.4},
    )

    raw = response.text
    cv_latex = _extract(raw, _CV_START, _CV_END)
    changes = _extract(raw, _CHANGES_START, _CHANGES_END)

    if not cv_latex:
        print("     WARNING: CV delimiters not found in Gemini response, saving raw output")
        cv_latex = raw.strip()
        changes = "*(Delimiter parsing failed - no changes log)*"

    return cv_latex, changes

# ---------------------------------------------------------------------------
# Per-person pipeline
# ---------------------------------------------------------------------------

def process_person(cfg: dict, all_jobs: list[dict], api_key: str, dry_run: bool) -> dict:
    name = cfg["name"]
    person_dir = DATA_DIR / cfg["folder"]
    cv_dir = person_dir / CV_SUBDIR
    jobs_dir = person_dir / "jobs"
    keywords = cfg["keywords"]

    stats = {"name": name, "matched": 0, "new": 0, "skipped": 0, "errors": 0}

    # Load CV and prompt
    cv_path = cv_dir / CV_FILENAME
    cv_tex = cv_path.read_text(encoding="utf-8") if cv_path.exists() else None
    if not cv_tex:
        print(f"  WARNING: {cv_path} not found, CV customization skipped for {name}")

    prompt_path = cv_dir / PROMPT_FILENAME
    if prompt_path.exists():
        system_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        print(f"  WARNING: {prompt_path} not found, using generic prompt")
        system_prompt = (
            "You are a CV tailoring assistant. Tailor EXPERIENCE and SKILLS to match the JD. "
            f"Output using {_CV_START}/{_CV_END} and {_CHANGES_START}/{_CHANGES_END} markers."
        )

    matched = [j for j in all_jobs if matches_keywords(j, keywords)]
    stats["matched"] = len(matched)
    print(f"  {len(matched)} jobs matched")

    if dry_run:
        for j in matched:
            print(f"    [{j['source']}] {j['title'][:80]}")
        return stats

    seen_ids = existing_job_ids(jobs_dir)
    num = next_job_number(jobs_dir)

    for job in matched:
        if job["job_source_id"] in seen_ids:
            stats["skipped"] += 1
            continue

        job_folder = jobs_dir / f"job_{num:02d}"
        job_folder.mkdir(parents=True, exist_ok=True)
        (job_folder / "job.json").write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"    Created {job_folder.name}: {job['title'][:60]}")

        if cv_tex and api_key:
            try:
                print(f"    Calling Gemini ({GEMINI_MODEL})...")
                cv_out, changes = customize_cv(cv_tex, job["description"], api_key, system_prompt)
                (job_folder / "CV_customized.tex").write_text(cv_out, encoding="utf-8")
                changes_header = (
                    f"# Changes Log\n\n"
                    f"**Job:** {job['title']}\n"
                    f"**Source:** {job['source']} | {job['url']}\n\n---\n\n"
                )
                (job_folder / "changes.md").write_text(changes_header + changes, encoding="utf-8")
                print(f"    Saved CV_customized.tex and changes.md")
                time.sleep(2)
            except Exception as e:
                print(f"    ERROR: {e}")
                stats["errors"] += 1

        stats["new"] += 1
        num += 1

    return stats

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Filter jobs and customize CVs per person")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--person", default=None, help="Process only this folder, e.g. 01_Thang")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv(BASE_DIR.parent / ".env")
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key and not args.dry_run:
        print("WARNING: GEMINI_API_KEY not set - CV customization will be skipped")

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}")
        sys.exit(1)

    persons = yaml.safe_load(config_path.read_text(encoding="utf-8")).get("persons", [])
    if args.person:
        persons = [p for p in persons if p["folder"] == args.person]
        if not persons:
            print(f"ERROR: folder '{args.person}' not in config")
            sys.exit(1)

    print("Loading crawled jobs...")
    all_jobs = load_all_jobs()
    print(f"  {len(all_jobs)} jobs loaded\n")

    all_stats = []
    for cfg in persons:
        print(f"Processing: {cfg['name']} ({cfg['folder']})")
        all_stats.append(process_person(cfg, all_jobs, api_key, args.dry_run))
        print()

    print("-" * 50)
    print("SUMMARY")
    for s in all_stats:
        print(f"  {s['name']}: {s['matched']} matched, {s['new']} new, "
              f"{s['skipped']} skipped, {s['errors']} errors")
    if not args.dry_run:
        print("\n  Review changes.md in each job folder before submitting.")


if __name__ == "__main__":
    main()
