from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, HttpUrl, SecretStr

class Settings(BaseSettings):
    # Configurações Notion
    notion_token: SecretStr
    notion_version: str = "2022-06-28"
    notion_property_mappings: dict = {
        "pdf_property": "Proposta PDF",
        "status_property": "Status Assinatura"
    }
    
    # Configurações ZapSign
    zapsign_token: SecretStr
    zapsign_api_url: HttpUrl = "https://api.zapsign.com.br/api/v1/docs"
    zapsign_default_lang: str = "pt-br"
    
    # Configurações da Aplicação
    api_base_url: HttpUrl
    webhook_secret: SecretStr | None = None
    debug_mode: bool = False
    request_timeout: int = 30  # segundos
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CORRETORA_",  # Prefixo para variáveis de ambiente
        case_sensitive=False
    )

    @field_validator("notion_version")
    def validate_notion_version(cls, v):
        supported_versions = ["2022-06-28", "2022-02-22"]
        if v not in supported_versions:
            raise ValueError(f"Versão Notion inválida. Use uma destas: {', '.join(supported_versions)}")
        return v

    @field_validator("zapsign_default_lang")
    def validate_zapsign_lang(cls, v):
        valid_langs = ["pt-br", "en", "es"]
        if v not in valid_langs:
            raise ValueError(f"Idioma inválido. Opções: {', '.join(valid_langs)}")
        return v

settings = Settings()