from fastapi import FastAPI, HTTPException, Request
import httpx
from pydantic import BaseModel
import base64
import os

app = FastAPI()

# Configurações (use variáveis de ambiente)
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
ZAPSIGN_TOKEN = os.getenv("ZAPSIGN_TOKEN")

class NotionPayload(BaseModel):
    page_id: str
    email: str
    whatsapp: str

@app.post("/senddoc")
async def send_doc(request: Request, payload: NotionPayload):
    try:
        # 1. Buscar a página no Notion para obter o PDF
        async with httpx.AsyncClient() as client:
            notion_response = await client.get(
                f"https://api.notion.com/v1/pages/{payload.page_id}",
                headers={
                    "Authorization": f"Bearer {NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28"
                }
            )
            notion_response.raise_for_status()
            notion_data = notion_response.json()

            # 2. Extrair URL do PDF da propriedade "Proposta PDF"
            proposta_pdf = notion_data["properties"]["Proposta PDF"]["files"][0]
            pdf_url = proposta_pdf["external"]["url"]

            # 3. Baixar o PDF (opcional, se ZapSign não aceitar URLs temporárias)
            pdf_response = await client.get(pdf_url)
            pdf_content = base64.b64encode(pdf_response.content).decode("utf-8")

            # 4. Enviar para o ZapSign
            zap_sign_payload = {
                "name": "Contrato de Seguro",  # Substitua por um campo dinâmico se necessário
                "email": payload.email,
                "phone": f"+{payload.whatsapp}",
                "doc_content": pdf_content,  # Ou use "doc_url": pdf_url se preferir
                "doc_name": "contrato.pdf",
                "signers": [{
                    "name": "Cliente",
                    "email": payload.email,
                    "phone": f"+{payload.whatsapp}"
                }]
            }

            zap_sign_response = await client.post(
                "https://api.zapsign.com.br/docs",
                json=zap_sign_payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {ZAPSIGN_TOKEN}"
                }
            )
            zap_sign_response.raise_for_status()

        return {"success": True, "data": zap_sign_response.json()}

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Erro ao processar documento: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )

# Para rodar: uvicorn main:app --reload