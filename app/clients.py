import requests
from typing import Optional
from .settings import settings

# Cabeçalhos comuns para Notion
NOTION_HEADERS = {
    "Authorization": f"Bearer {settings.notion_token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def notion_get_page(page_id: str):
    return requests.get(
        f"https://api.notion.com/v1/pages/{page_id}", headers=NOTION_HEADERS
    ).json()

def notion_update(page_id: str, status: str, doc_token: Optional[str] = None):
    props = {"Status Assinatura": {"select": {"name": status}}}
    if doc_token:
        props["Doc Token"] = {"rich_text": [{"text": {"content": doc_token}}]}
    requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=NOTION_HEADERS,
        json={"properties": props},
    )

def zapsign_create(name: str, pdf_url: str, signer_name: str, signer_email: str):
    payload = {
        "name": name,
        "url_pdf": pdf_url,
        "signers": [{"name": signer_name, "email": signer_email}],
    }
    res = requests.post(
        "https://api.zapsign.com.br/api/v1/docs",
        json=payload,
        headers={"Authorization": f"Bearer {settings.zapsign_token}"},
        timeout=30,
    )
    res.raise_for_status()
    return res.json()["token"]
