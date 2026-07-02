import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    GEMINI_API_KEY: str
    ANTHROPIC_API_KEY: str
    MASTER_PROFILE_SHA256: str
    DB_PATH: str = "jobs.db"
    DAILY_BUDGET_CAP: float = 5.0
    USER_DATA_DIR: str = "./browser_profiles"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

config = Settings()
