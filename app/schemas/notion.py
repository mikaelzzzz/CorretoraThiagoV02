import re
from pydantic import BaseModel, Field, validator
from app.settings import settings

class NotionPayload(BaseModel):
    page_id: str    = Field(..., alias=settings.notion_property_mappings["page_id"])
    whatsapp: str   = Field(
        ..., 
        alias=settings.notion_property_mappings["whatsapp"], 
        min_length=10, 
        max_length=13
    )
    client_name: str = Field(..., alias=settings.notion_property_mappings["client_name"])
    email: str       = Field(..., alias=settings.notion_property_mappings["email"])

    @validator('whatsapp')
    def validate_whatsapp(cls, v: str) -> str:
        # Remove todos os caracteres não numéricos
        cleaned = re.sub(r'\D', '', v)
        
        # Valida comprimento (10-13 dígitos)
        if len(cleaned) not in (10, 11, 12, 13):
            raise ValueError("Número deve ter entre 10 e 13 dígitos")
            
        # Adiciona código do país se necessário
        if not cleaned.startswith('55'):
            cleaned = f'55{cleaned}'  # Assume Brasil como padrão
            
        return cleaned

    class Config:
        allow_population_by_field_name = True
        extra = "ignore"  # Ignora campos extras não mapeados
