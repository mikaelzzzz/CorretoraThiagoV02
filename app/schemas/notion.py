import re
from pydantic import BaseModel, Field, ConfigDict, field_validator

class NotionPayload(BaseModel):
    # Propriedades exatas do Notion, sem usar um dicionário de alias
    page_id: str = Field(..., alias="Page ID")
    whatsapp: str = Field(..., alias="WhatsApp")
    client_name: str = Field(..., alias="Nome do Cliente")
    email: str = Field(..., alias="Email")

    @field_validator("whatsapp", mode="before")
    def validate_whatsapp(cls, v: str) -> str:
        # Remove tudo que não for dígito
        cleaned = re.sub(r"\D", "", v)
        # Valida comprimento (10-13 dígitos)
        if len(cleaned) not in (10, 11, 12, 13):
            raise ValueError("Número deve ter entre 10 e 13 dígitos")
        # Adiciona código do país se faltar
        if not cleaned.startswith("55"):
            cleaned = f"55{cleaned}"
        return cleaned

    # Configuração Pydantic v2 para suportar aliases e ignorar campos extras
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore"
    )
