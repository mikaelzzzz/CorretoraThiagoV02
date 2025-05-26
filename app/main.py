# app/main.py

import re
import base64
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from app.schemas.notion import NotionPayload
from app.settings import settings
import httpx

# Configuração inicial do app
app = FastAPI(title="Corretora 3.0 API", version="1.0.0")

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tokens carregados do settings
NOTION_TOKEN = settings.notion_token.get_secret_value()
ZAPSIGN_TOKEN = settings.zapsign_token.get_secret_value()

# Tratamento de erros de validação para logar o corpo da requisição
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.body()
    logger.error(f"ValidationError: errors={exc.errors()}, body={body.decode('utf-8')}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body.decode('utf-8')}
    )

class Signer(BaseModel):
    name: str
    email: str
    auth_mode: str = "assinaturaTela"
    phone_country: str = "55"
    phone_number: str
    send_automatic_email: bool = True
    send_automatic_whatsapp: bool = True

    @field_validator('phone_number', mode='before')
    def validate_phone_number(cls, v: str) -> str:
        cleaned = re.sub(r"\D", "", v)
        if len(cleaned) not in (11, 13):
            raise ValueError("Número deve ter 11 (DDD+9 dígitos) ou 13 dígitos (com código país)")
        if not cleaned.startswith('55'):
            cleaned = '55' + cleaned
        return cleaned

@app.post("/create-document", response_model=dict)
async def create_document(request: Request):
    """
    Cria documento no ZapSign a partir de evento do Notion
    """
    # 1. Extrair e validar dados do webhook do Notion
    try:
        event = await request.json()
        props = event['data']['properties']
        clean = {
            'Page ID':         props['Page ID']['formula']['string'],
            'WhatsApp':        props['WhatsApp']['rich_text'][0]['plain_text'],
            'Nome do Cliente': props['Nome do Cliente']['title'][0]['plain_text'],
            'Email':           props['Email']['email'],
        }
        payload = NotionPayload.model_validate(clean)
        logger.info(f"[DEBUG] Payload construído: {payload.dict(by_alias=True)}")
    except Exception as e:
        logger.error(f"Erro ao extrair dados do Notion: {e}")
        raise HTTPException(status_code=422, detail=f"Erro ao extrair dados: {e}")

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            # 2. Buscar dados do Notion (para obter URL do PDF)
            try:
                notion_response = await client.get(
                    f"{settings.notion_base_url}/pages/{payload.page_id}",
                    headers={
                        'Authorization': f"Bearer {NOTION_TOKEN}",
                        'Notion-Version': settings.notion_api_version,
                    }
                )
                notion_response.raise_for_status()
                notion_data = notion_response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Falha na Notion API: {e.response.text}")
                raise HTTPException(status_code=502, detail=f"Falha no Notion: {e.response.text}")

            # 3. Processar PDF
            try:
                proposta_pdf = notion_data['properties']['Proposta PDF']['files'][0]
                pdf_url = (
                    proposta_pdf.get('external', {}).get('url')
                    or proposta_pdf.get('file', {}).get('url')
                )
                if not pdf_url or not pdf_url.startswith('http'):
                    raise ValueError("URL do PDF inválida")

                pdf_response = await client.get(pdf_url)
                pdf_response.raise_for_status()
                content = pdf_response.content
                if not content or b'%PDF' not in content[:8]:
                    raise ValueError("Conteúdo não parece ser um PDF válido")

                pdf_content = base64.b64encode(content).decode('utf-8')
            except (KeyError, ValueError) as e:
                logger.error(f"Erro ao processar PDF: {e}")
                raise HTTPException(status_code=422, detail=f"Erro no PDF: {e}")

            # 4. Integração com ZapSign
            try:
                signer = Signer(
                    name=payload.client_name,
                    email=payload.email,
                    phone_number=payload.whatsapp
                )
                zap_payload = {
                    'name': f"Contrato {payload.client_name}",
                    'base64_pdf': pdf_content,
                    'lang': 'pt-br',
                    'signers': [signer.dict()],
                    'metadata': [
                        {'key': 'notion_page_id', 'value': payload.page_id},
                        {'key': 'client_email', 'value': payload.email}
                    ],
                }
                response = await client.post(
                    f"{settings.zapsign_base_url}/docs",
                    json=zap_payload,
                    headers={
                        'Authorization': f"Bearer {ZAPSIGN_TOKEN}",
                        'Content-Type': 'application/json'
                    }
                )
                response.raise_for_status()
                data = response.json()
                return {
                    'status': 'success',
                    'document_id': data['open_id'],
                    'sign_url': data['signers'][0]['sign_url']
                }
            except httpx.HTTPStatusError as e:
                logger.error(f"Erro na ZapSign: {e.response.text}")
                raise HTTPException(status_code=502, detail=f"Erro ZapSign: {e.response.text}")

    except Exception as e:
        logger.error(f"Erro interno crítico: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno: {e}")