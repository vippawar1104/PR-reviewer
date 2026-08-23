import base64
import binascii

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_app_id: str
    github_private_key: str
    github_webhook_secret: str
    gemini_api_key: str
    database_url: str = ""

    @property
    def github_private_key_pem(self) -> str:
        """
        Accepts either the raw multi-line PEM (fine for a local .env file) or a
        base64-encoded PEM (recommended for deployment platforms, since several
        of them mangle or reject multi-line env var values).
        """
        key = self.github_private_key.strip()
        if key.startswith("-----BEGIN"):
            return key
        try:
            return base64.b64decode(key).decode()
        except (binascii.Error, UnicodeDecodeError) as e:
            raise ValueError(
                "GITHUB_PRIVATE_KEY is neither a raw PEM nor valid base64"
            ) from e


settings = Settings()
