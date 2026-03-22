# 🎯 Job Extraction - Standalone Test Guide

This guide shows you how to run **ONLY the job extraction** functionality without the full application.

---

## 📋 Prerequisites

### 1. **Install Dependencies**

First, install only the required packages for job extraction:

```bash
pip install selenium webdriver-manager langchain-core langchain-community langchain-openai faiss-cpu loguru pyyaml
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

### 2. **Get API Key**

Use your **FPT AI Marketplace** API key for **GLM-4.7**.

---

## 🚀 Step-by-Step Instructions

### **Step 1: Set Your API Key**

Choose **ONE** of these methods:

#### Option A: Environment Variable (Recommended)

```bash
# Windows (Command Prompt)
set LLM_API_KEY=your-fpt-llm-api-key

# Windows (PowerShell)
$env:LLM_API_KEY="your-fpt-llm-api-key"

# Linux/Mac
export LLM_API_KEY="your-fpt-llm-api-key"
```

#### Option B: Use `data_folder\secrets.yaml` (same as app flow)

Create `data_folder\secrets.yaml` with:

```yaml
llm_api_key: "your-fpt-llm-api-key"
```

---

### **Step 2: Configure LLM Model for GLM-4.7**

In `config.py`, ensure:

```python
LLM_MODEL_TYPE = 'openai'
LLM_MODEL = 'GLM-4.7'
LLM_EMBEDDING_MODEL = None
LLM_API_URL = 'https://mkp-api.fptcloud.com'
```

If your provider supports embeddings with a specific model name, set:

```python
LLM_EMBEDDING_MODEL = "your-supported-embedding-model"
```

---

### **Step 3: Run the Extraction**

```bash
python test_job_extraction.py
```

No URL prompt and no cookie-path prompt are needed.

This script is now fixed to:
- Group URL: `https://www.facebook.com/groups/ithotjobs.tuyendungit.vieclamcntt.susudev/?sorting_setting=CHRONOLOGICAL`
- Cookie file: `facebook.com.cookies.json` (in project root)

It will:
- auto-login by cookies
- clear all files in `debug_steps` at start
- crawl only containers matching class substring: `xdj266r x14z9mp xat24cr x1lziwak xexx8yu xyri2b x18d9i69 x1c1uobl`
- while scrolling, collect latest 10 posts
- for each post, extract content from div with class containing: `xdj266r x14z9mp xat24cr x1lziwak x1vvkbs`
- use AI to filter only remote-job posts
- write final output to `facebook_remote_posts.json`
- write debug artifacts after each step to `debug_steps`

Cookie file format (JSON list or object with `cookies`):

```json
[
  {
    "name": "c_user",
    "value": "123456",
    "domain": ".facebook.com",
    "path": "/",
    "secure": true,
    "httpOnly": false
  },
  {
    "name": "xs",
    "value": "your-session",
    "domain": ".facebook.com",
    "path": "/",
    "secure": true,
    "httpOnly": true
  }
]
```

---

## 📊 What Happens During Extraction

```
1. 🌐 Browser initialized (headless Chrome)
   └─ Navigates to the job URL

2. 📄 HTML content extracted
   └─ Gets full page source

3. 🧠 Retrieval context prepared
   └─ Splits text into chunks
   └─ Tries FAISS + embeddings if available
   └─ Falls back to chunk-based context if embeddings are unavailable

4. 🔍 Information extracted using LLM:
   ├─ Company name
   ├─ Job role/title
   ├─ Location
   ├─ Job description summary
   └─ Recruiter email (if available)

5. ✅ Results displayed
```

---

## 📤 Example Output

```
==================================================================
         EXTRACTION RESULTS
==================================================================

📌 Company:     Google
💼 Role:        Senior Software Engineer
📍 Location:    Mountain View, CA (Remote available)
🔗 URL:         https://www.linkedin.com/jobs/view/12345678/
📧 Recruiter:   recruiter@google.com

📝 Description:
----------------------------------------------------------------------
We are looking for a Senior Software Engineer to join our team...
[Full description summary here]
==================================================================
```

---

## 🛠️ Troubleshooting

### **Issue: `text-embedding-ada-002` not found / 404**

Cause: your endpoint/model doesn't support OpenAI default embeddings model.

Fix options:
- Keep `LLM_EMBEDDING_MODEL = None` (default in this repo now). The parser will auto-fallback without embeddings.
- Or set `LLM_EMBEDDING_MODEL` to a provider-supported embedding model name.

### **Issue: "ChromeDriver not found"**

```bash
pip install webdriver-manager
```

The script auto-downloads ChromeDriver.

### **Issue: "API key invalid"**

- Check your API key is correct
- Verify it has sufficient credits/quota
- Ensure no extra spaces in the key

### **Issue: "Module not found"**

```bash
# Make sure you're in the project root directory
cd Jobs_Applier_AI_Agent_AIHawk

# Install dependencies
pip install -r requirements.txt
```

### **Issue: "FAISS not found"**

```bash
# For CPU-only (recommended for testing)
pip install faiss-cpu

# For GPU support
pip install faiss-gpu
```

### **Issue: Browser opens but can't access URL**

- Check your internet connection
- Some sites block headless browsers (LinkedIn, Indeed may require login)
- Try a simpler job board or public job posting

---

## 🎯 Test with Different URLs

### Good URLs to Test:

- ✅ Company career pages (e.g., `https://jobs.apple.com/...`)
- ✅ Public job boards
- ✅ Job aggregator sites

### Challenging URLs:

- ⚠️ LinkedIn (requires login for full access)
- ⚠️ Indeed (may have anti-bot protection)
- ⚠️ Password-protected pages

---

## 📝 Customize the Script

### Extract Additional Fields

Edit `test_job_extraction.py` and add custom extraction:

```python
# In the extract_job_from_url function, add:

# Extract salary information
logger.info("  - Extracting salary...")
salary_question = "What is the salary range mentioned in this job description?"
salary = parser._extract_information(salary_question, "salary compensation")
job.salary = salary

# Extract required skills
logger.info("  - Extracting skills...")
skills_question = "What are the required skills for this position?"
skills = parser._extract_information(skills_question, "required skills qualifications")
job.skills = skills
```

---

## 🔧 Notes for GLM-4.7 on FPT Marketplace

- This project uses OpenAI-compatible client wiring (`ChatOpenAI`, `OpenAIEmbeddings`) with custom `LLM_API_URL`.
- Your endpoint must support both chat-completions and embeddings for extraction pipeline to work.
- If embeddings are not supported by your endpoint/model, the FAISS extraction step will fail.

---

## 💡 Next Steps

After successful extraction, you can:

- Save results to a database
- Process multiple URLs in batch
- Generate tailored resumes (use the full app)
- Integrate with your own job application workflow

---

## 📚 Key Files Reference

| File                                                      | Purpose                |
| --------------------------------------------------------- | ---------------------- |
| `test_job_extraction.py`                                  | **Main script to run** |
| `src/libs/resume_and_cover_builder/llm/llm_job_parser.py` | Core extraction logic  |
| `src/job.py`                                              | Job data model         |
| `src/utils/chrome_utils.py`                               | Browser automation     |
| `config.py`                                               | LLM configuration      |

---

## ✅ Success Checklist

- [ ] Dependencies installed
- [ ] API key configured
- [ ] `config.py` edited for your LLM provider
- [ ] Chrome/Chromium installed on system
- [ ] Internet connection active
- [ ] Job URL ready to test

**You're ready to go! Run `python test_job_extraction.py`** 🚀
