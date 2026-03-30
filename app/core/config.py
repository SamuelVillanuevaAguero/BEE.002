from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database
    DB_HOST: str = ""
    DB_PORT: int = 0
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_NAME: str = ""
    DB_SSL_CA: str = ""

    # App
    APP_ENV: str = ""
    APP_DEBUG: bool = False

    # Scheduler
    SCHEDULER_TIMEZONE: str = ""
    SCHEDULER_COALESCE: bool = True
    SCHEDULER_MAX_INSTANCES: int = 3

    # HTTP Retries
    HTTP_RETRY_MAX: int = 2
    HTTP_RETRY_BACKOFF: float = 1.0
    HTTP_RETRY_ON_STATUS: str = "429,502,503,504"
    HTTP_TIMEOUT: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def DATABASE_URL(self) -> str:
        url = (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
        if self.APP_ENV == "production":
            url += f"?ssl_ca={self.DB_SSL_CA}"
        return url

    @property
    def APSCHEDULER_URL(self) -> str:
        """URL for APScheduler jobstore (uses the same DB)."""
        return self.DATABASE_URL


settings = Settings()