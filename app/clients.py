# app/clients.py

import base64
import logging
import requests
from typing import Optional
from fastapi import HTTPException
from .settings import settings

log = logging.getLogger("uvicorn.error")

# Cabeçalhos Notion
NOTION_HEADERS = {
    "Authorization": f"Bearer {settings.notion_token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def zapsign_create(name: str, pdf_url: str, signer_name: str, signer_email: str) -> str:
    """
    Versão corrigida e otimizada:
    - Tratamento adequado de URLs do Notion
    - Validação de campos
    - Melhor tratamento de erros
    """
    try:
        # 1) Obter URL válido do Notion
        log.info(f"Obtendo PDF de: {pdf_url}")
        
        # Buscar metadados do arquivo
        file_meta = requests.get(
            pdf_url,
            headers=NOTION_HEADERS,
            timeout=10
        )
        file_meta.raise_for_status()
        
        # Extrair URL temporário válido
        if not (signed_url := file_meta.json().get('url')):
            raise ValueError("URL do PDF não encontrado na resposta do Notion")
            
        log.info(f"URL temporário obtido: {signed_url[:60]}...")

        # 2) Baixar conteúdo do PDF
        pdf_response = requests.get(signed_url, timeout=30)
        pdf_response.raise_for_status()
        
        # 3) Validar PDF
        if not pdf_response.content.startswith(b'%PDF-'):
            raise ValueError("Arquivo não parece ser um PDF válido")

        # 4) Converter para base64
        b64_pdf = base64.b64encode(pdf_response.content).decode('utf-8')
        if len(b64_pdf) < 100:
            raise ValueError("Base64 do PDF inválido")

        # 5) Criar payload para ZapSign
        payload = {
            "name": name,
            "base64_pdf": b64_pdf,
            "signers": [{
                "name": signer_name,
                "email": signer_email,
                "auth_mode": "assinaturaTela",
                "send_automatic_email": True
            }],
            "lang": "pt-br"
        }

        # 6) Enviar para ZapSign
        headers = {
            "Authorization": f"Bearer {settings.zapsign_token}",
            "Content-Type": "application/json"
        }
        
        log.info("Criando documento na ZapSign...")
        response = requests.post(
            "https://api.zapsign.com.br/api/v1/docs",
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()

        # 7) Processar resposta
        response_data = response.json()
        if not (doc_token := response_data.get('token')):
            raise ValueError("Token do documento não encontrado na resposta")
            
        log.info(f"Documento criado com sucesso! Token: {doc_token[:8]}...")
        return doc_token

    except requests.exceptions.RequestException as e:
        error_msg = f"Erro HTTP {e.response.status_code}" if e.response else str(e)
        log.error(f"Falha na integração: {error_msg}")
        raise HTTPException(
            status_code=502,
            detail=f"Erro na comunicação com serviços externos: {error_msg}"
        ) from e

    except Exception as e:
        log.error(f"Erro crítico: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno no processamento: {str(e)}"
        ) from e