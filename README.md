# AIHawk: The first Jobs Applier AI Web Agent


AIHawk's core architecture remains **open source**, allowing developers to inspect and extend the codebase. However, due to copyright considerations, we have removed all third‑party provider plugins from this repository.

## Installation

```bash
uv venv
uv pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

## Build tex cv
Quick build command
```
docker run --rm -v $(pwd)/data_folder:/src -v $(pwd)/data_folder/output:/out -w /src texlive/texlive \
  pdflatex -interaction=nonstopmode -output-directory=/out nam-cv.tex
```

The app will prompt you to choose between generating a generic resume, a job-tailored resume, or a tailored cover letter, then guide you through style selection.

## Configuration

Set LLM provider and model in `config.py`:
- `LLM_MODEL_TYPE` — `openai`, `claude`, `ollama`, `gemini`, `huggingface`, or `perplexity`
- `LLM_MODEL` — model name (e.g., `gpt-4o-mini`)
- `LLM_API_URL` — optional custom base URL for OpenAI-compatible APIs (e.g., OpenRouter)

User data goes in `data_folder/` (see `data_folder_example/` for templates):
- `secrets.yaml` — LLM API key
- `work_preferences.yaml` — job preferences (experience levels, job types, blacklists)
- `plain_text_resume.yaml` — your resume content in YAML format

## Testing

```bash
pytest
```

---


AIHawk has been featured by major media outlets for revolutionizing how job seekers interact with the job market:

[**Business Insider**](https://www.businessinsider.com/aihawk-applies-jobs-for-you-linkedin-risks-inaccuracies-mistakes-2024-11)
[**TechCrunch**](https://techcrunch.com/2024/10/10/a-reporter-used-ai-to-apply-to-2843-jobs/)
[**Semafor**](https://www.semafor.com/article/09/12/2024/linkedins-have-nots-and-have-bots)
[**Dev.by**](https://devby.io/news/ya-razoslal-rezume-na-2843-vakansii-po-17-v-chas-kak-ii-boty-vytesnyaut-ludei-iz-protsessa-naima.amp)
[**Wired**](https://www.wired.it/article/aihawk-come-automatizzare-ricerca-lavoro/)
[**The Verge**](https://www.theverge.com/2024/10/10/24266898/ai-is-enabling-job-seekers-to-think-like-spammers)
[**Vanity Fair**](https://www.vanityfair.it/article/intelligenza-artificiale-candidature-di-lavoro)
[**404 Media**](https://www.404media.co/i-applied-to-2-843-roles-the-rise-of-ai-powered-job-application-bots/)

