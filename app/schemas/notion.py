# app/schemas/notion.py

import re
from pydantic import BaseModel, Field, ConfigDict, field_validator

class NotionPayload(BaseModel):
    # Propriedades exatas do seu banco no Notion
    page_id: str = Field(
        ...,
        alias="Page ID"
    )
    whatsapp: str = Field(
        ...,
        alias="WhatsApp"
    )
    client_name: str = Field(
        ...,
        alias="Nome do Cliente"
    )
    email: str = Field(
        ...,
        alias="Email"
    )

    @field_validator("whatsapp", mode="before")
    def validate_whatsapp(cls, v: str) -> str:
        # Limpa tudo que não for dígito
        cleaned = re.sub(r"\D", "", v)
        # Deve ter entre 10 e 13 dígitos
        if len(cleaned) not in (10, 11, 12, 13):
            raise ValueError("Número deve ter entre 10 e 13 dígitos")
        # Adiciona '55' se faltar o código do Brasil
        if not cleaned.startswith("55"):
            cleaned = f"55{cleaned}"
        return cleaned

    model_config = ConfigDict(
        populate_by_name=True,  # permite popular pelos nomes dos campos
        extra="ignore"          # ignora quaisquer outras props no JSON
    )
