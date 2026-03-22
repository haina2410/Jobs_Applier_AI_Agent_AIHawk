# In this file, you can set the configurations of the app.

from src.utils.constants import DEBUG, ERROR, LLM_MODEL, OPENAI

#config related to logging must have prefix LOG_
LOG_LEVEL = 'DEBUG'
LOG_SELENIUM_LEVEL = ERROR
LOG_TO_FILE = True
LOG_TO_CONSOLE = True

MINIMUM_WAIT_TIME_IN_SECONDS = 60

JOB_APPLICATIONS_DIR = "job_applications"
JOB_SUITABILITY_SCORE = 7

JOB_MAX_APPLICATIONS = 5
JOB_MIN_APPLICATIONS = 1

LLM_MODEL_TYPE = 'openai'
LLM_MODEL = 'GLM-4.7'
# Optional: set this only if your endpoint supports embeddings with a custom model name.
# Example: 'text-embedding-v3' (depends on your provider support)
LLM_EMBEDDING_MODEL = None
# Only required for OLLAMA models
LLM_API_URL = 'https://mkp-api.fptcloud.com'
