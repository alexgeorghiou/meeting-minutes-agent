"""Environment-driven configuration.

Every setting can be supplied as an environment variable prefixed with ``MINUTES_``
(for example ``MINUTES_LLM_PROVIDER=anthropic``) or through a ``.env`` file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["fake", "anthropic", "openai"]
TranscriberBackend = Literal["fake", "openai", "local"]
JobStoreBackend = Literal["memory", "sqlite"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINUTES_", env_file=".env", extra="ignore")

    # LLM
    llm_provider: LLMProvider = "fake"
    llm_model: str | None = Field(
        default=None, description="Override the provider's default model name."
    )
    llm_temperature: float = 0.0
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None

    # Transcription
    transcriber: TranscriberBackend = "fake"
    whisper_model: str = "whisper-1"
    local_whisper_model: str = "small"
    local_whisper_device: str = "auto"
    max_upload_mb: int = 100

    # Pipeline
    chunk_words: int = 1200
    chunk_overlap_words: int = 100
    max_review_attempts: int = 2

    # Job store
    job_store: JobStoreBackend = "memory"
    sqlite_path: Path = Path("data/jobs.sqlite3")
    upload_dir: Path = Path("data/uploads")

    # API
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Exporters
    github_token: SecretStr | None = None
    github_repo: str | None = Field(default=None, description="owner/name")
    github_api_url: str = "https://api.github.com"
    github_labels: list[str] = Field(default_factory=lambda: ["action-item"])

    jira_base_url: str | None = Field(default=None, description="https://your-site.atlassian.net")
    jira_email: str | None = None
    jira_api_token: SecretStr | None = None
    jira_project_key: str | None = None
    jira_issue_type: str = "Task"

    @property
    def github_configured(self) -> bool:
        return bool(self.github_token and self.github_repo)

    @property
    def jira_configured(self) -> bool:
        return bool(
            self.jira_base_url and self.jira_email and self.jira_api_token and self.jira_project_key
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
