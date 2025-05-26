# app/clients.py

import base64
import logging
import requests
from typing import Optional
from .settings import settings

log = logging.getLogger("uvicorn.error")

# Cabeçalhos Notion
NOTION_HEADERS = {
    "Authorization": f"Bearer {settings.notion_token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def notion_get_page(page_id: str) -> dict:
    """Busca página no Notion com tratamento de erros."""
    try:
        resp = requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        log.error(f"Erro ao buscar página {page_id}: {str(e)}")
        raise

def notion_update(page_id: str, status: str, doc_token: Optional[str] = None) -> None:
    """Atualiza página no Notion com tratamento de erros."""
    try:
        props = {"Status Assinatura": {"select": {"name": status}}}
        if doc_token:
            props["Doc Token"] = {"rich_text": [{"text": {"content": doc_token}}]}
            
        resp = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            json={"properties": props},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.error(f"Erro ao atualizar página {page_id}: {str(e)}")
        raise

def zapsign_create(name: str, pdf_url: str, signer_name: str, signer_email: str) -> str:
    """
    Cria documento na ZapSign com:
    1. Download seguro do PDF do Notion
    2. Tratamento de erros aprimorado
    3. Headers customizados
    """
    try:
        # 1) Download do PDF com headers do Notion
        log.info(f"Baixando PDF: {pdf_url}")
        pdf_resp = requests.get(
            pdf_url,
            headers={
                "Authorization": f"Bearer {settings.notion_token}",
                "User-Agent": "Mozilla/5.0 (Compatível; MeuBot/1.0)"
            },
            timeout=30
        )
        pdf_resp.raise_for_status()
        log.info("PDF baixado com sucesso")

        # 2) Conversão para base64
        b64_pdf = base64.b64encode(pdf_resp.content).decode()
        
        # 3) Criação do documento na ZapSign
        payload = {
            "name": name,
            "base64_pdf": b64_pdf,
            "signers": [{
                "name": signer_name,
                "email": signer_email,
                "auth_mode": "assinaturaTardia"  # Modo de autenticação
            }]
        }
        
        headers = {
            "Authorization": f"Bearer {settings.zapsign_token}",
            "Content-Type": "application/json"
        }
        
        log.info("Enviando para ZapSign...")
        res = requests.post(
            "https://api.zapsign.com.br/api/v1/docs",
            json=payload,
            headers=headers,
            timeout=30
        )
        res.raise_for_status()
        log.info(f"Resposta ZapSign: {res.text}")

        # 4) Extração do token
        data = res.json()
        if not (token := data.get("token")):
            raise ValueError("Token não encontrado na resposta da ZapSign")
            
        return token

    except requests.exceptions.RequestException as e:
        error_msg = f"Erro HTTP {e.response.status_code}" if e.response else str(e)
        log.error(f"Falha na ZapSign: {error_msg} - Resposta: {e.response.text if e.response else ''}")
        raise HTTPException(502, "Falha na comunicação com ZapSign") from e
        
    except Exception as e:
        log.error(f"Erro inesperado: {str(e)}", exc_info=True)
        raise HTTPException(500, "Erro interno no processamento") from e