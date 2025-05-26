# app/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    """Configurações de ambiente para Corretora 3.0"""
    # Notion API
    notion_token: SecretStr
    notion_database_id: str
    notion_api_version: str = "2022-06-28"
    notion_base_url: str = "https://api.notion.com/v1"
    notion_property_mappings: dict[str, str] = {
        "page_id":     "Page ID",
        "whatsapp":    "WhatsApp",
        "client_name": "Nome do Cliente",
        "email":       "Email",
    }

    # ZapSign API
    zapsign_token: SecretStr
    zapsign_base_url: str = "https://api.zapsign.com.br/api/v1"

    # Timeouts e valores gerais
    http_timeout_seconds: int = 30

    # Carrega variáveis de ambiente de .env com prefixo CORRETORA_
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CORRETORA_",
        case_sensitive=False
    )

# Instância única de configurações
settings = Settings()
