from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite+aiosqlite:///./resume.db"
    openai_api_key: str = ""
    resume_model: str = "gpt-4.1-mini"
    interviewee_model: str = "gpt-4.1-mini"
    interviewer_model: str = "gpt-4.1-mini"
    api_timeout_seconds: float = 90
    max_output_tokens: int = 5000
    # Explicit estimates only. Leave unset for models with unconfigured pricing.
    input_usd_per_million: float | None = None
    output_usd_per_million: float | None = None
    web_search_usd_per_call: float | None = None
    max_iteration_tokens: int = 150000
    cors_origin: str = "http://localhost:3000"
    api_access_token: str = ""

@lru_cache
def settings():
    return Settings()
