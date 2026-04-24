"""应用配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for uninitialized environments
    def load_dotenv(path: Path) -> None:
        """当 `python-dotenv` 不可用时使用的最小 `.env` 加载器。"""
        if not path.exists():
            return

        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

from app.core.constants import (
    APP_NAME,
    DEFAULT_ENV,
    DEFAULT_LOG_LEVEL,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_TIMEOUT,
)

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


def get_sqlite_database_path() -> Path:
    """主业务 SQLite 文件路径（会话、runs、trace 索引、V2 等共用）。

    与 Chroma 向量库存储（默认 ``.chroma/``）分离，不由本函数配置。
    未设置环境变量时统一为仓库根目录下的 ``.simple_code_agent.sqlite3``。
    """
    custom = (os.getenv("SQLITE_DB_PATH") or "").strip()
    if custom:
        return Path(custom).expanduser()
    return BASE_DIR / ".simple_code_agent.sqlite3"


@dataclass(frozen=True)
class Settings:
    """从环境变量中读取的强类型应用配置。"""

    app_name: str = APP_NAME
    app_env: str = os.getenv("APP_ENV", DEFAULT_ENV)
    log_level: str = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    llm_base_url: str = os.getenv("LLM_BASE_URL", DEFAULT_OPENAI_BASE_URL)
    llm_auth_mode: str = os.getenv("LLM_AUTH_MODE", "auto").lower()
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_service_token: str = os.getenv("LLM_SERVICE_TOKEN", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_timeout: int = int(os.getenv("LLM_TIMEOUT", str(DEFAULT_OPENAI_TIMEOUT)))
    llm_reasoning_param_style: str = os.getenv("LLM_REASONING_PARAM_STYLE", "none").lower()
    write_validation_mode: str = os.getenv("WRITE_VALIDATION_MODE", "strict").lower()
    session_id: str = os.getenv("SESSION_ID", "")
    # 顶层统一使用 workdir 语义，默认只读取 WORKDIR。
    workdir: str = os.getenv("WORKDIR", "")


settings = Settings()

_runtime_llm_overrides: dict[str, str] = {}


def get_effective_llm_base_url() -> str:
    """获取当前生效的 LLM_BASE_URL（优先运行时覆盖）。"""
    return _runtime_llm_overrides.get("llm_base_url") or settings.llm_base_url


def get_effective_llm_model() -> str:
    """获取当前生效的 LLM_MODEL（优先运行时覆盖）。"""
    return _runtime_llm_overrides.get("llm_model") or settings.llm_model


def update_llm_runtime_settings(*, llm_base_url: str, llm_model: str) -> None:
    """更新运行时 LLM 配置，并持久化到 .env。"""
    base_url = llm_base_url.strip()
    model = llm_model.strip()
    _runtime_llm_overrides["llm_base_url"] = base_url
    _runtime_llm_overrides["llm_model"] = model
    os.environ["LLM_BASE_URL"] = base_url
    os.environ["LLM_MODEL"] = model
    _upsert_env_value("LLM_BASE_URL", base_url)
    _upsert_env_value("LLM_MODEL", model)


def _upsert_env_value(key: str, value: str) -> None:
    """在 .env 中更新或追加配置项。"""
    lines: list[str]
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    updated = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        existing_key = stripped.split("=", 1)[0].strip()
        if existing_key == key:
            lines[idx] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
