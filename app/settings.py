# app/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from app.settings import settings


class Settings(BaseSettings):
    # Notion
    notion_token: SecretStr
    notion_database_id: str
    notion_property_mappings: dict = {  # 👈 Adicione esta linha
        "page_id": "Page ID",
        "whatsapp": "WhatsApp",
        "client_name": "Client Name",
        "email": "Email"
    }

    # ZapSign
    zapsign_token: SecretStr

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CORRETORA_",
        case_sensitive=False
    )

settings = Settings()