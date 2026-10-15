from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables / the .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    nvidia_api_key: str | None = None
    nvidia_model: str = "openai/gpt-oss-20b"
    llm_timeout_seconds: float = 30.0
    avg_consult_minutes: int = 10
    seed_demo_data: bool = False
    # Folder holding opd.db and supply_chain.db (default: <project>/data)
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"


@lru_cache
def get_settings() -> Settings:
    return Settings()
