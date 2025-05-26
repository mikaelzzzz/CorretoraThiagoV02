from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator, constr
import httpx
import base64
import os
from typing import Optional
import logging

# Configuração inicial do app
app = FastAPI(title="Corretora 3.0 API", version="1.0.0")

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variáveis de ambiente
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
ZAPSIGN_TOKEN = os.getenv("ZAPSIGN_TOKEN")

class Signer(BaseModel):
    name: str
    email: str
    auth_mode: str = "assinaturaTela"
    phone_country: str = "55"
    phone_number: str
    send_automatic_email: bool = True
    send_automatic_whatsapp: bool = True

class NotionPayload(BaseModel):
    page_id: str
    email: str
    whatsapp: constr(min_length=11, max_length=13)
    client_name: str

    @validator('whatsapp')
    def validate_whatsapp(cls, v):
        cleaned = v.strip() \
            .replace(" ", "") \
            .replace("-", "") \
            .replace("+", "") \
            .replace("(", "") \
            .replace(")", "")
        
        if not cleaned.isdigit():
            raise ValueError("Número de WhatsApp inválido")
        if len(cleaned) not in (11, 13):
            raise ValueError("Número deve ter 11 (DDD+9 dígitos) ou 13 dígitos (com código país)")
        
        return cleaned

@app.post("/create-document", response_model=dict)
async def create_document(payload: NotionPayload):
    """
    Cria documento no ZapSign a partir de dados do Notion
    
    - **page_id**: ID da página no Notion
    - **email**: Email do cliente
    - **whatsapp**: Número do WhatsApp (apenas dígitos)
    - **client_name**: Nome completo do cliente
    """
    try:
        logger.info(f"Iniciando processo para página: {payload.page_id}")
        
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Buscar dados do Notion
            try:
                notion_response = await client.get(
                    f"https://api.notion.com/v1/pages/{payload.page_id}",
                    headers={
                        "Authorization": f"Bearer {NOTION_TOKEN}",
                        "Notion-Version": "2022-06-28"
                    }
                )
                notion_response.raise_for_status()
                notion_data = notion_response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Erro no Notion: {e.response.text}")
                raise HTTPException(
                    status_code=502,
                    detail="Falha na comunicação com o Notion"
                )

            # 2. Processar PDF
            try:
                proposta_pdf = notion_data["properties"]["Proposta PDF"]["files"][0]
                pdf_url = (
                    proposta_pdf["external"]["url"] 
                    if "external" in proposta_pdf 
                    else proposta_pdf["file"]["url"]
                )
                
                # Validar URL
                if not pdf_url.startswith("http"):
                    raise ValueError("URL do PDF inválida")

                pdf_response = await client.get(pdf_url)
                pdf_response.raise_for_status()
                
                # Validar PDF
                if not pdf_response.content.startswith(b'%PDF-'):
                    raise ValueError("Arquivo não é um PDF válido")

                pdf_content = base64.b64encode(pdf_response.content).decode("utf-8")
                
            except (KeyError, ValueError) as e:
                logger.error(f"Erro no PDF: {str(e)}")
                raise HTTPException(
                    status_code=422,
                    detail="Arquivo PDF inválido ou não encontrado"
                )

            # 3. Preparar e enviar para ZapSign
            try:
                signers = [Signer(
                    name=payload.client_name,
                    email=payload.email,
                    phone_number=payload.whatsapp[-11:]
                ).dict()]

                response = await client.post(
                    "https://api.zapsign.com.br/api/v1/docs",
                    json={
                        "name": f"Contrato {payload.client_name}",
                        "base64_pdf": pdf_content,
                        "lang": "pt-br",
                        "signers": signers,
                        "brand_name": "Corretora 3.0",
                        "metadata": [{"key": "notion_page_id", "value": payload.page_id}]
                    },
                    headers={
                        "Authorization": f"Bearer {ZAPSIGN_TOKEN}",
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                response_data = response.json()
                
                return {
                    "status": "success",
                    "document_id": response_data["open_id"],
                    "sign_url": response_data["signers"][0]["sign_url"]
                }
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Erro no ZapSign: {e.response.text}")
                raise HTTPException(
                    status_code=502,
                    detail="Falha na comunicação com o ZapSign"
                )

    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno no processamento"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "default",
                },
            },
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                },
            },
            "root": {
                "level": "INFO",
                "handlers": ["console"]
            }
        }
    )