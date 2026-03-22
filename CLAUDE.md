# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AIHawk is an AI-powered job application tool that uses LLMs (OpenAI, Claude, Ollama, Gemini, HuggingFace, Perplexity) to generate tailored resumes and cover letters. Users provide their resume in YAML format, select a visual style, and the system generates job-tailored PDF documents.

## Commands

```bash
# Install dependencies
uv pip install -r requirements.txt

# Run the application (interactive mode)
uv run python main.py

# Run the LinkedIn crawler (scheduled/automated mode)
uv run python -m src.crawlers.runner

# Run tests
uv run pytest
```

## Architecture

### Entry Point & Flow

`main.py` is both the entry point and contains configuration/validation logic (`ConfigValidator`, `FileManager`). The flow is:

1. Validate data folder structure and YAML configs
2. Interactive prompt (via `inquirer`) — user picks: generic resume, tailored resume, or cover letter
3. `StyleManager` prompts for CSS style selection
4. `ResumeFacade` orchestrates: browser → job extraction → LLM generation → HTML → PDF

### Key Components

**`main.py`** — Entry point + `ConfigValidator` (validates all YAML configs with 50+ rules) + `FileManager` (ensures required files exist, maps paths)

**`src/libs/resume_and_cover_builder/resume_facade.py`** — Central orchestrator (Facade pattern). Coordinates browser automation, style selection, LLM interaction, and PDF generation. Methods: `create_resume_pdf()`, `create_resume_pdf_job_tailored()`, `create_cover_letter()`

**`src/libs/resume_and_cover_builder/resume_generator.py`** — Generates HTML content by calling LLM classes (`LLMResumer`, `LLMResumeJobDescription`, `LLMCoverLetterJobDescription`) and applying CSS styling

**`src/libs/llm_manager.py`** — Abstract `AIModel` base class with concrete implementations for each LLM provider (OpenAI, Claude, Gemini, Ollama, etc.). Uses LangChain for orchestration.

**`src/libs/resume_and_cover_builder/llm/llm_job_parser.py`** — Extracts job details from HTML using FAISS vector store + embeddings for semantic search

**`src/libs/resume_and_cover_builder/style_manager.py`** — Manages CSS styles from `resume_style/` directory. Parses style metadata from CSS first-line comments: `/* StyleName $ AuthorLink */`

**`src/libs/resume_and_cover_builder/config.py`** — `GlobalConfig` singleton managing paths, HTML templates, and settings

### Crawlers

**`src/crawlers/`** — Plugin-based job crawling system. Runs on a schedule (cron) to search job boards, scrape listings, and auto-generate tailored resumes/cover letters.

- `base.py` — `BaseCrawler` ABC with template `crawl()` method (search → dedup → scrape)
- `linkedin.py` — `LinkedInCrawler` using cookie auth + undetected-chromedriver. Searches via URL params, parses job cards, scrapes full descriptions.
- `tracker.py` — `Tracker` class for JSON-based dedup across runs (`data_folder/crawled_jobs.json`)
- `config.py` — `CrawlerConfig` dataclass with filter mappings (experience level, job type, work type, date posted)
- `runner.py` — Entry point. Loads config, runs enabled crawlers, feeds jobs to `ResumeFacade` for PDF generation.

**Config:** `data_folder/crawler_config.yaml` (see `data_folder_example/` for template). LinkedIn cookies (`li_at`, `li_rm`) go in `secrets.yaml`.

### Data Models

- `src/resume_schemas/resume.py` — `Resume` Pydantic model that parses YAML directly via `Resume(yaml_str)`
- `src/resume_schemas/job_application_profile.py` — `JobApplicationProfile` dataclass with nested models for self-identification, legal authorization, work preferences
- `src/job.py` — `Job` dataclass (role, company, location, link, description)

### Prompt Templates

LLM prompts live in `src/libs/resume_and_cover_builder/` subdirectories:
- `resume_prompt/strings_feder-cr.py` — generic resume prompts
- `resume_job_description_prompt/strings_feder-cr.py` — job-tailored resume prompts
- `cover_letter_prompt/strings_feder-cr.py` — cover letter prompts

### Configuration

**`config.py`** (top-level) — App settings: `LLM_MODEL_TYPE`, `LLM_MODEL`, `JOB_SUITABILITY_SCORE`, `JOB_MAX_APPLICATIONS`, logging config

**User data** lives in `data_folder/` (gitignored):
- `secrets.yaml` — LLM API key + LinkedIn cookies (`li_at`, `li_rm`)
- `work_preferences.yaml` — Job preferences (experience levels, job types, blacklists)
- `plain_text_resume.yaml` — Resume content
- `crawler_config.yaml` — Crawler settings (filters, rate limiting, output options)
- `crawled_jobs.json` — Tracker for dedup across crawler runs
- `output/` — Generated PDFs

Example configs are in `data_folder_example/`.

### PDF Generation

HTML→PDF conversion uses Chrome CDP (Chrome DevTools Protocol) via Selenium. `src/utils/chrome_utils.py` handles browser initialization with undetected-chromedriver and the HTML-to-PDF pipeline.

### Logging

Uses loguru (`src/logging.py`) with dual file/console output. LLM API calls are separately tracked to `open_ai_calls.json` via `LoggerChatModel` in `src/libs/resume_and_cover_builder/utils.py`.

## Branch Strategy

Per CONTRIBUTING.md: `main` (production) → `develop` (integration) → `feature/*` branches → PR flow. Minimum 2 maintainer approvals for merges.
