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

# Handler para erros de validação e log do corpo da requisição
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
    Cria documento no ZapSign e atualiza status no Notion para 'Enviado'
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

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        # 2. Buscar URL do PDF
        try:
            notion_resp = await client.get(
                f"{settings.notion_base_url}/pages/{payload.page_id}",
                headers={
                    'Authorization': f"Bearer {NOTION_TOKEN}",
                    'Notion-Version': settings.notion_api_version,
                }
            )
            notion_resp.raise_for_status()
            notion_data = notion_resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Falha Notion API: {e.response.text}")
            raise HTTPException(502, f"Falha no Notion: {e.response.text}")

        # 3. Processar PDF
        try:
            files = notion_data['properties']['Proposta PDF']['files']
            file_item = files[0]
            pdf_url = file_item.get('external', {}).get('url') or file_item.get('file', {}).get('url')
            if not pdf_url or not pdf_url.startswith('http'):
                raise ValueError("URL do PDF inválida")
            pdf_resp = await client.get(pdf_url)
            pdf_resp.raise_for_status()
            content = pdf_resp.content
            if not content or b'%PDF' not in content[:8]:
                raise ValueError("Conteúdo não parece ser um PDF válido")
            pdf_b64 = base64.b64encode(content).decode('utf-8')
        except Exception as e:
            logger.error(f"Erro no PDF: {e}")
            raise HTTPException(422, f"Erro no PDF: {e}")

        # 4. Envia para ZapSign
        try:
            signer = Signer(
                name=payload.client_name,
                email=payload.email,
                phone_number=payload.whatsapp
            )
            zap_payload = {
                'name': f"Contrato {payload.client_name}",
                'base64_pdf': pdf_b64,
                'lang': 'pt-br',
                'signers': [signer.dict()],
                'metadata': [ {'key': 'notion_page_id', 'value': payload.page_id} ]
            }
            zap_resp = await client.post(
                f"{settings.zapsign_base_url}/docs",
                json=zap_payload,
                headers={ 'Authorization': f"Bearer {ZAPSIGN_TOKEN}", 'Content-Type': 'application/json' }
            )
            zap_resp.raise_for_status()
            zap_data = zap_resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro ZapSign: {e.response.text}")
            raise HTTPException(502, f"Erro ZapSign: {e.response.text}")

        # 5. Atualiza status para 'Enviado'
        try:
            patch_payload = { 'properties': { 'Status Assinatura': { 'select': {'name':'Enviado'} } } }
            upd = await client.patch(
                f"{settings.notion_base_url}/pages/{payload.page_id}",
                json=patch_payload,
                headers={
                    'Authorization': f"Bearer {NOTION_TOKEN}",
                    'Notion-Version': settings.notion_api_version,
                    'Content-Type': 'application/json'
                }
            )
            upd.raise_for_status()
        except Exception:
            logger.error("Falha ao atualizar status para Enviado no Notion")

    return { 'status':'success', 'document_id': zap_data['open_id'], 'sign_url': zap_data['signers'][0]['sign_url'] }

@app.post("/zapsign-webhook")
async def zapsign_webhook(request: Request):
    """
    Recebe webhook do ZapSign e atualiza Notion para 'Assinado'
    """
    data = await request.json()
    # Extrai page_id do metadata
    metadata = data.get('metadata', [])
    page_id = next((m['value'] for m in metadata if m.get('key')=='notion_page_id'), None)
    if not page_id:
        logger.error("Webhook ZapSign sem metadata notion_page_id")
        return JSONResponse(status_code=400, content={"detail":"Missing notion_page_id"})

    # Atualiza status no Notion
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        try:
            patch = { 'properties': { 'Status Assinatura': { 'select': {'name':'Assinado'} } } }
            resp = await client.patch(
                f"{settings.notion_base_url}/pages/{page_id}",
                json=patch,
                headers={
                    'Authorization': f"Bearer {NOTION_TOKEN}",
                    'Notion-Version': settings.notion_api_version,
                    'Content-Type': 'application/json'
                }
            )
            resp.raise_for_status()
            return {"status":"updated"}
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro ao atualizar para Assinado: {e.response.text}")
            raise HTTPException(status_code=502, detail=f"Falha Notion update: {e.response.text}")
