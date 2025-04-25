import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str
    TOKEN_ACCESS_EXPIRE_MINUTES: str
    TOKEN_SECRET: str
    TOKEN_ALGORITHM: str
    API_KEY: str

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", ".env")
    )


@lru_cache
def get_env():
    return Settings()
