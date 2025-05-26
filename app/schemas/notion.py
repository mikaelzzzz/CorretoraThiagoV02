import re
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.settings import settings

class NotionPayload(BaseModel):
    page_id: str = Field(
        ...,
        alias=settings.notion_property_mappings["page_id"]
    )
    whatsapp: str = Field(
        ...,
        alias=settings.notion_property_mappings["whatsapp"]
    )
    client_name: str = Field(
        ...,
        alias=settings.notion_property_mappings["client_name"]
    )
    email: str = Field(
        ...,
        alias=settings.notion_property_mappings["email"]
    )

    @field_validator("whatsapp", mode="before")
    def validate_whatsapp(cls, v: str) -> str:
        # Remove tudo que não é dígito
        cleaned = re.sub(r"\D", "", v)
        # Valida comprimento (10-13 dígitos)
        if len(cleaned) not in (10, 11, 12, 13):
            raise ValueError("Número deve ter entre 10 e 13 dígitos")
        # Adiciona código do país se faltar
        if not cleaned.startswith("55"):
            cleaned = f"55{cleaned}"
        return cleaned

    # Configuração Pydantic v2
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore"
    )
