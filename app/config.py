from dataclasses import dataclass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{PROJECT_ROOT / 'data' / 'local-sales-ai.sqlite3'}"


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Local Sales AI")
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


settings = Settings()
