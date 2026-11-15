"""Settings loaded from environment variables / .env. Secrets never come from prompts."""
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    portal_base_url: str = "https://transindus-portal.onrender.com"
    website_url: str = "http://localhost:8700/"  # the Meridian landing page (web/); the logo links here
    portal_user: str = ""
    portal_password: SecretStr = SecretStr("")
    team_key: SecretStr = SecretStr("")

    max_requests_per_second: float = 2.0

    llm_provider: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    vision_model: str = ""

    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_host: str = "https://cloud.langfuse.com"


def get_settings() -> Settings:
    return Settings()
