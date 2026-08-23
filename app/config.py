from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_app_id: str
    github_private_key: str
    github_webhook_secret: str
    gemini_api_key: str
    database_url: str = ""


settings = Settings()
