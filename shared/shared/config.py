"""
Shared chat-model factory + .env loading.

Apps call load_project_env(PROJECT_ROOT), then get_chat_llm().
Database URLs, RAG, and world paths stay in each app's config.py.
"""

from pathlib import Path
import os

from dotenv import load_dotenv

# Set in load_project_env. Do not derive from this file — uv installs
# shared into .venv, so __file__ is not under the git root.
REPO_ROOT: Path | None = None

OPENAI_API_KEY = None
ANTHROPIC_API_KEY = None
GOOGLE_API_KEY = None
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1"
LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-4.1-mini"

_DEFAULT_MODELS = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-4-5",
    "gemini": "gemini-2.0-flash",
}

_chat_llm = None


def _refresh() -> None:
    global OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY
    global OLLAMA_BASE_URL, OLLAMA_MODEL, LLM_PROVIDER, LLM_MODEL
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
    LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    LLM_MODEL = resolve_llm_model()


def load_project_env(project_root: Path) -> None:
    """Load Gen-AI/.env, then the app's .env (overrides). Refresh key globals."""
    global REPO_ROOT
    project_root = Path(project_root).resolve()
    REPO_ROOT = project_root.parent
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(project_root / ".env", override=True)
    _refresh()


def resolve_llm_model(provider: str | None = None) -> str:
    """Pick a model id. Ignore leftover gpt-* names when the provider is not OpenAI."""
    provider = (provider or (os.getenv("LLM_PROVIDER") or "openai")).strip().lower()
    raw = (os.getenv("LLM_MODEL") or "").strip()
    ollama = os.getenv("OLLAMA_MODEL", "llama3.1")
    defaults = {**_DEFAULT_MODELS, "ollama": ollama}
    if provider == "openai":
        return raw or defaults["openai"]
    if provider == "ollama":
        if raw and not raw.startswith("gpt-"):
            return raw
        return ollama
    if raw and not raw.startswith("gpt-"):
        return raw
    return defaults.get(provider, raw or defaults["openai"])


def get_chat_llm():
    """Process-wide chat client. Extra providers are imported only if you switch."""
    global _chat_llm
    if _chat_llm is not None:
        return _chat_llm

    _refresh()
    provider = LLM_PROVIDER
    model = resolve_llm_model(provider)
    print(f"LLM: {provider} / {model}")

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is missing in .env")
        _chat_llm = ChatOpenAI(model=model, api_key=OPENAI_API_KEY)
        return _chat_llm

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise ImportError("LLM_PROVIDER=anthropic needs: uv add langchain-anthropic") from exc
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is missing in .env")
        _chat_llm = ChatAnthropic(model=model, api_key=ANTHROPIC_API_KEY)
        return _chat_llm

    if provider in {"gemini", "google"}:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise ImportError("LLM_PROVIDER=gemini needs: uv add langchain-google-genai") from exc
        if not GOOGLE_API_KEY:
            raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is missing in .env")
        _chat_llm = ChatGoogleGenerativeAI(model=model, google_api_key=GOOGLE_API_KEY)
        return _chat_llm

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise ImportError("LLM_PROVIDER=ollama needs: uv add langchain-ollama") from exc
        _chat_llm = ChatOllama(model=model, base_url=OLLAMA_BASE_URL)
        return _chat_llm

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. Use openai, anthropic, gemini, or ollama."
    )
