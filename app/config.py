from dataclasses import dataclass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{PROJECT_ROOT / 'data' / 'local-sales-ai.sqlite3'}"


def _normalize_base_path(value: str) -> str:
    normalized = value.strip()
    if not normalized or normalized == "/":
        return ""
    return "/" + normalized.strip("/")


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Local Sales AI")
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    base_path: str = _normalize_base_path(os.getenv("APP_BASE_PATH", ""))
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", str(PROJECT_ROOT / "data" / "uploads")))


settings = Settings()
