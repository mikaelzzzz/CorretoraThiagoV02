from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    notion_token: str
    notion_db_id: str
    zapsign_token: str
    host_url: str  # Domínio público da sua API

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

settings = Settings()
