from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator, constr
from app.schemas.notion import NotionPayload
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
    """
    try:
        # Log detalhado do payload recebido
        logger.info(f"\n[DEBUG] Payload recebido: {payload.dict()}")
        print(f"[TEST] Iniciando processamento para: {payload.client_name}")

        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Buscar dados do Notion
            try:
                logger.info(f"[TEST] Buscando página {payload.page_id} no Notion")
                notion_response = await client.get(
                    f"https://api.notion.com/v1/pages/{payload.page_id}",
                    headers={
                        "Authorization": f"Bearer {NOTION_TOKEN}",
                        "Notion-Version": "2022-06-28"
                    }
                )
                logger.debug(f"[TEST] Resposta do Notion: {notion_response.status_code}")
                notion_response.raise_for_status()
                notion_data = notion_response.json()
                print(f"[TEST] Dados do Notion obtidos com sucesso")

            except httpx.HTTPStatusError as e:
                logger.error(f"[ERRO] Notion API: {e.response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Falha no Notion: {e.response.text}"
                )

            # 2. Processar PDF
            try:
                print(f"[TEST] Processando PDF...")
                proposta_pdf = notion_data["properties"]["Proposta PDF"]["files"][0]
                pdf_url = (
                    proposta_pdf["external"]["url"] 
                    if "external" in proposta_pdf 
                    else proposta_pdf["file"]["url"]
                )
                
                # Validação reforçada
                logger.info(f"[TEST] URL do PDF: {pdf_url}")
                if not pdf_url.startswith("http"):
                    raise ValueError("URL inválida")
                if "notion.so" not in pdf_url:
                    print("[ALERTA] URL do PDF pode não ser do Notion")

                pdf_response = await client.get(pdf_url)
                logger.debug(f"[TEST] Status PDF: {pdf_response.status_code}")
                
                # Validação do conteúdo
                if len(pdf_response.content) == 0:
                    raise ValueError("PDF vazio")
                if not pdf_response.content.startswith(b'%PDF-'):
                    raise ValueError("Cabeçalho PDF inválido")

                pdf_content = base64.b64encode(pdf_response.content).decode("utf-8")
                print(f"[TEST] PDF codificado ({len(pdf_content)} caracteres base64)")

            except (KeyError, ValueError) as e:
                logger.error(f"[ERRO] PDF: {str(e)}")
                raise HTTPException(
                    status_code=422,
                    detail=f"Erro no PDF: {str(e)}"
                )

            # 3. Integração com ZapSign
            try:
                print(f"[TEST] Preparando payload para ZapSign...")
                signers = [Signer(
                    name=payload.client_name,
                    email=payload.email,
                    phone_number=payload.whatsapp[-11:]
                ).dict()]

                zap_payload = {
                    "name": f"Contrato {payload.client_name}",
                    "base64_pdf": pdf_content,
                    "lang": "pt-br",
                    "signers": signers,
                    "metadata": [
                        {"key": "notion_page_id", "value": payload.page_id},
                        {"key": "client_email", "value": payload.email}
                    ]
                }
                logger.debug(f"[TEST] Payload ZapSign: {zap_payload}")

                response = await client.post(
                    "https://api.zapsign.com.br/api/v1/docs",
                    json=zap_payload,
                    headers={
                        "Authorization": f"Bearer {ZAPSIGN_TOKEN}",
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                response_data = response.json()
                print(f"[TEST] Documento criado: {response_data['open_id']}")

                return {
                    "status": "success",
                    "document_id": response_data["open_id"],
                    "sign_url": response_data["signers"][0]["sign_url"],
                    "debug_info": {  # Apenas para testes
                        "pdf_size": len(pdf_content),
                        "notion_page": payload.page_id
                    }
                }
                
            except httpx.HTTPStatusError as e:
                logger.error(f"[ERRO] ZapSign: {e.response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Erro ZapSign: {e.response.text}"
                )

    except Exception as e:
        logger.error(f"[ERRO CRÍTICO] {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )