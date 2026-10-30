from functools import lru_cache
from pydantic import Field, AliasChoices, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )
    database_url: str = "sqlite+aiosqlite:///./resume.db"
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "RESUME_OPENAI_KEY", "OPENAI_API_KEY", "openai_api_key"
        ),
    )
    codex_binary: str = Field(default="codex", validation_alias="RESUME_CODEX_BINARY")
    codex_home: str = Field(
        default=".codex-runtime", validation_alias="RESUME_CODEX_HOME"
    )
    codex_model: str | None = None
    codex_resume_model: str | None = None
    codex_interviewee_model: str | None = None
    codex_interviewer_model: str | None = None
    codex_timeout_seconds: float = 180
    resume_model: str = "gpt-4.1-mini"
    interviewee_model: str = "gpt-4.1-mini"
    interviewer_model: str = "gpt-4.1-mini"
    api_timeout_seconds: float = 90
    max_output_tokens: int = 5000
    # Explicit estimates only. Leave unset for models with unconfigured pricing.
    input_usd_per_million: float | None = None
    output_usd_per_million: float | None = None
    web_search_usd_per_call: float | None = None

    @field_validator(
        "input_usd_per_million",
        "output_usd_per_million",
        "web_search_usd_per_call",
        mode="before",
    )
    @classmethod
    def empty_price(cls, value):
        return None if value == "" else value

    max_iteration_tokens: int = Field(default=150000, ge=1000)
    cors_origin: str = "http://localhost:3000"
    api_access_token: str = ""


@lru_cache
def settings():
    return Settings()
