"""
Twin-specific settings. LLM factory lives in shared.config.

.env: Gen-AI/.env, then digital-twin-agent/.env (overrides).
"""

from pathlib import Path
import os

from shared.config import get_chat_llm, load_project_env, resolve_llm_model
from shared import config as shared_config

PROJECT_ROOT = Path(__file__).resolve().parent
load_project_env(PROJECT_ROOT)

REPO_ROOT = shared_config.REPO_ROOT
OPENAI_API_KEY = shared_config.OPENAI_API_KEY
ANTHROPIC_API_KEY = shared_config.ANTHROPIC_API_KEY
GOOGLE_API_KEY = shared_config.GOOGLE_API_KEY
OLLAMA_BASE_URL = shared_config.OLLAMA_BASE_URL
OLLAMA_MODEL = shared_config.OLLAMA_MODEL
LLM_PROVIDER = shared_config.LLM_PROVIDER
LLM_MODEL = shared_config.LLM_MODEL

DATA_DIR = PROJECT_ROOT / "data"
TOKEN_CHUNKS = int(os.getenv("TOKEN_CHUNKS", "800"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://twin:twin@localhost:5432/digital_twin",
)
