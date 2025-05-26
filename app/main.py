# app/main.py

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from .settings import settings
from .clients import notion_update, zapsign_create, NOTION_HEADERS
import requests
import logging

log = logging.getLogger("uvicorn.error")

class SendDocPayload(BaseModel):
    page_id: str
    nome: str
    email: EmailStr
    proposta_pdf: dict

class ZapSignWebhookPayload(BaseModel):
    event: str
    doc_token: str

# Crie a instância do FastAPI com o nome 'app'
app = FastAPI(title="Notion ↔ ZapSign Integration")

@app.post("/senddoc", response_model=dict)
async def send_doc(payload: SendDocPayload, bg: BackgroundTasks):
    """
    Recebe JSON via botão do Notion, envia o PDF à ZapSign
    e atualiza Status Assinatura → Enviado no Notion.
    """
    try:
        files = payload.proposta_pdf.get("files", [])
        pdf_url = files[0]["file"]["url"]
    except (IndexError, KeyError, TypeError):
        log.error("Estrutura inválida em proposta_pdf: %r", payload.proposta_pdf)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Campo 'proposta_pdf' mal formatado ou vazio.",
        )

    try:
        doc_token = zapsign_create(
            payload.nome, pdf_url, payload.nome, payload.email
        )
    except Exception as exc:
        log.exception("Erro ao criar doc na ZapSign")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Falha ao comunicar com a ZapSign.",
        )

    bg.add_task(notion_update, payload.page_id, "Enviado", doc_token)
    return {"ok": True, "doc_token": doc_token}

@app.post("/zapsign/webhook", status_code=200)
async def zapsign_webhook(req: Request):
    """
    Recebe webhooks da ZapSign e atualiza o Notion.
    """
    try:
        body = await req.json()
        payload = ZapSignWebhookPayload(**body)
    except Exception:
        log.error("Webhook ZapSign payload inválido: %r", await req.body())
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "JSON de webhook inválido.",
        )

    if payload.event != "document_signed":
        return JSONResponse(status_code=200, content={"ignored": True})

    query = {
        "filter": {
            "property": "Doc Token",
            "rich_text": {"contains": payload.doc_token},
        }
    }
    res = requests.post(
        f"https://api.notion.com/v1/databases/{settings.notion_db_id}/query",
        headers=NOTION_HEADERS,
        json=query,
        timeout=10,
    ).json()

    results = res.get("results") or []
    if not results:
        log.warning("Doc Token não encontrado no Notion: %s", payload.doc_token)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Página não encontrada")

    page_id = results[0]["id"]
    notion_update(page_id, "Assinado")
    return {"ok": True}