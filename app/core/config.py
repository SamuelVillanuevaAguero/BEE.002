from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "scheduler_db"

    # App
    APP_ENV: str = "development"
    APP_DEBUG: bool = True

    # Scheduler
    SCHEDULER_TIMEZONE: str = "America/Mexico_City"
    SCHEDULER_COALESCE: bool = True
    SCHEDULER_MAX_INSTANCES: int = 3

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def APSCHEDULER_URL(self) -> str:
        """URL for APScheduler jobstore (uses the same DB)."""
        return self.DATABASE_URL


settings = Settings()