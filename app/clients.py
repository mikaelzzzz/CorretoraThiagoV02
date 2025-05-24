# app/clients.py

import base64
import requests
from typing import Optional
from .settings import settings

# Cabeçalhos comuns para Notion
NOTION_HEADERS = {
    "Authorization": f"Bearer {settings.notion_token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def notion_get_page(page_id: str) -> dict:
    """
    Busca a página no Notion pelo ID.
    """
    resp = requests.get(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=NOTION_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

def notion_update(page_id: str, status: str, doc_token: Optional[str] = None) -> None:
    """
    Atualiza Status Assinatura (e opcionalmente o Doc Token) na página do Notion.
    """
    props = {"Status Assinatura": {"select": {"name": status}}}
    if doc_token is not None:
        props["Doc Token"] = {
            "rich_text": [
                {"text": {"content": doc_token}}
            ]
        }
    resp = requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=NOTION_HEADERS,
        json={"properties": props},
        timeout=10,
    )
    resp.raise_for_status()

def zapsign_create(name: str, pdf_url: str, signer_name: str, signer_email: str) -> str:
    """
    Cria um documento na ZapSign enviando o PDF como base64.
    Baixa o PDF do Notion (com autenticação), converte para base64,
    e chama o endpoint /docs da ZapSign.
    """
    # 1) Baixar o PDF do Notion
    resp = requests.get(pdf_url, headers=NOTION_HEADERS, timeout=30)
    resp.raise_for_status()
    # 2) Converte o conteúdo para base64
    b64_pdf = base64.b64encode(resp.content).decode()

    # 3) Monta e envia o payload para a ZapSign
    payload = {
        "name": name,
        "base64_pdf": b64_pdf,
        "signers": [{"name": signer_name, "email": signer_email}],
    }
    headers = {"Authorization": f"Bearer {settings.zapsign_token}"}
    res = requests.post(
        "https://api.zapsign.com.br/api/v1/docs",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if not res.ok:
        # Se falhar, expõe o status e a mensagem para facilitar o debug
        raise Exception(f"ZapSign error {res.status_code}: {res.text}")

    data = res.json()
    token = data.get("token")
    if not token:
        raise Exception(f"ZapSign response missing token: {data}")

    return token
