# app/main.py

from fastapi import FastAPI, BackgroundTasks, HTTPException
from .settings import settings
from .clients import notion_update, zapsign_create, NOTION_HEADERS
import requests

app = FastAPI(title="Notion ↔ ZapSign Integration")

@app.post("/senddoc")
async def send_doc(payload: dict, bg: BackgroundTasks):
    """
    Recebe o JSON enviado pelo botão do Notion (Enviar webhook),
    contendo todas as propriedades da linha, inclusive:
      - page_id           (Page ID)
      - nome              (Nome do Cliente)
      - email             (Email)
      - proposta_pdf      (Proposta PDF)
    Envia o PDF para a ZapSign e atualiza Status Assinatura → Enviado.
    """
    try:
        page_id      = payload["page_id"]
        nome_doc     = payload["nome"]
        signer_name  = nome_doc
        signer_email = payload["email"]
        # 'proposta_pdf' vem como objeto com chave 'files'
        files_prop   = payload["proposta_pdf"]
        pdf_url      = files_prop["files"][0]["file"]["url"]
    except (KeyError, IndexError, TypeError):
        raise HTTPException(400, "Payload inválido ou campos ausentes no JSON do Notion.")

    # Cria o documento na ZapSign
    doc_token = zapsign_create(nome_doc, pdf_url, signer_name, signer_email)
    # Atualiza Notion em background
    bg.add_task(notion_update, page_id, "Enviado", doc_token)
    return {"ok": True, "doc_token": doc_token}


@app.post("/zapsign/webhook")
async def zapsign_webhook(payload: dict):
    """
    Recebe o webhook da ZapSign. Se event == "document_signed",
    faz query na database do Notion buscando a página cujo
    Doc Token *contém* o token, e atualiza Status Assinatura → Assinado.
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
