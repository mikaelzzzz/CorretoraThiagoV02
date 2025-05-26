from pydantic import BaseModel, Field
from app.settings import settings

class NotionPayload(BaseModel):
    page_id: str = Field(alias=settings.notion_property_mappings["page_id"])
    whatsapp: str = Field(alias=settings.notion_property_mappings["whatsapp"])
    client_name: str = Field(alias=settings.notion_property_mappings["client_name"])
    email: str = Field(alias=settings.notion_property_mappings["email"])

    class Config:
        allow_population_by_field_name = True
        extra = "ignore"  # Ignora campos extras não mapeados