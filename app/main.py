from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import base64
import os
from typing import List, Optional

app = FastAPI()

# Configurações (usar variáveis de ambiente)
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
    require_cpf: bool = False
    lock_phone: bool = True

class NotionPayload(BaseModel):
    page_id: str
    email: str
    whatsapp: str
    client_name: str

@app.post("/create-document")
async def create_document(payload: NotionPayload):
    try:
        # 1. Buscar página no Notion
        async with httpx.AsyncClient() as client:
            # Obter PDF do Notion
            notion_response = await client.get(
                f"https://api.notion.com/v1/pages/{payload.page_id}",
                headers={
                    "Authorization": f"Bearer {NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28"
                }
            )
            notion_response.raise_for_status()
            notion_data = notion_response.json()

            # Extrair e converter PDF para base64
            proposta_pdf = notion_data["properties"]["Proposta PDF"]["files"][0]
            pdf_url = proposta_pdf["external"]["url"]
            pdf_response = await client.get(pdf_url)
            base64_pdf = base64.b64encode(pdf_response.content).decode("utf-8")

            # 2. Preparar signatários
            signers = [Signer(
                name=payload.client_name,
                email=payload.email,
                phone_number=payload.whatsapp[-11:],  # Assume DDD + 9 dígitos
            ).dict()]

            # 3. Criar payload para ZapSign
            zap_sign_payload = {
                "name": f"Contrato {payload.client_name}",
                "base64_pdf": base64_pdf,
                "lang": "pt-br",
                "signers": signers,
                "disable_signer_emails": False,
                "brand_name": "Sua Corretora",
                "signature_order_active": False,
                "allow_refuse_signature": False,
                "metadata": [{"key": "origin", "value": "notion_automation"}]
            }

            # 4. Enviar para ZapSign
            zap_sign_response = await client.post(
                "https://api.zapsign.com.br/api/v1/docs",
                json=zap_sign_payload,
                headers={
                    "Authorization": f"Bearer {ZAPSIGN_TOKEN}",
                    "Content-Type": "application/json"
                }
            )
            zap_sign_response.raise_for_status()

            return {
                "status": "success",
                "document": zap_sign_response.json(),
                "sign_url": zap_sign_response.json()["signers"][0]["sign_url"]
            }

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Erro na integração: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )

# Para executar: uvicorn main:app --reload