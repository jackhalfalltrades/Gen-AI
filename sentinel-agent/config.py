"""
Sentinel-specific settings. LLM factory lives in shared.config.

.env: Gen-AI/.env, then sentinel-agent/.env (overrides).
"""

import os
from pathlib import Path

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

WORLD = PROJECT_ROOT / "world"
SCENARIOS = WORLD / "scenarios"
OUT_DIR = PROJECT_ROOT / "data" / "generated"
DATA_DIR = PROJECT_ROOT / "data"

_raw_db = os.getenv(
    "DATABASE_URL",
    "postgresql://sentinel:sentinel@localhost:5433/sentinel",
)
DATABASE_URL = _raw_db.replace("postgresql+psycopg://", "postgresql://", 1)

SENTINEL_MCP_URL = os.getenv("SENTINEL_MCP_URL", "http://127.0.0.1:8090")
