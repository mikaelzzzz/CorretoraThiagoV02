# app/main.py

from fastapi import FastAPI, BackgroundTasks, HTTPException
from .settings import settings
from .clients import notion_get_page, notion_update, zapsign_create, NOTION_HEADERS
import requests

app = FastAPI(title="Notion ↔ ZapSign Integration")

@app.get("/debug/page/{page_id}")
async def debug_page(page_id: str):
    """
    Retorna o JSON completo da página do Notion.
    Útil para inspecionar nomes exatos das propriedades.
    """
    return notion_get_page(page_id)


@app.post("/senddoc")
async def send_doc(page_id: str, bg: BackgroundTasks):
    """
    Recebe um page_id, busca no Notion o PDF e campos,
    envia para a ZapSign, e atualiza Status Assinatura → Enviado.
    """
    page = notion_get_page(page_id)
    props = page.get("properties")
    if not props:
        raise HTTPException(400, "Não foi possível ler as propriedades da página no Notion.")

    try:
        pdf_url      = props["Proposta PDF"]["files"][0]["file"]["url"]
        nome_doc     = props["Nome do Cliente"]["title"][0]["plain_text"]
        signer_name  = nome_doc
        signer_email = props["Email"]["email"]
    except (KeyError, IndexError):
        raise HTTPException(400, "Campos obrigatórios ausentes no Notion.")

    doc_token = zapsign_create(nome_doc, pdf_url, signer_name, signer_email)
    bg.add_task(notion_update, page_id, "Enviado", doc_token)
    return {"ok": True, "doc_token": doc_token}


@app.post("/zapsign/webhook")
async def zapsign_webhook(payload: dict):
    """
    Recebe webhook da ZapSign. Se event == "document_signed",
    busca página no Notion cujo Doc Token *contém* o token,
    e atualiza Status Assinatura → Assinado.
    """
    if payload.get("event") != "document_signed":
        return {"ignored": True}

    token = payload.get("doc_token")
    if not token:
        raise HTTPException(400, "Payload inválido: falta 'doc_token'.")

    query = {
        "filter": {
            "property": "Doc Token",
            "rich_text": {"contains": token},
        }
    }

    res = requests.post(
        f"https://api.notion.com/v1/databases/{settings.notion_db_id}/query",
        headers=NOTION_HEADERS,
        json=query,
    ).json()

    results = res.get("results") or []
    if not results:
        raise HTTPException(404, "Página não encontrada")

    page_id = results[0]["id"]
    notion_update(page_id, "Assinado")
    return {"ok": True}
