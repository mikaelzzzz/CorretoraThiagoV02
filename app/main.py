from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator, constr
import httpx
import base64
import os
from typing import Optional

app = FastAPI()

# Configurações
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

class NotionPayload(BaseModel):
    page_id: str
    email: str
    whatsapp: constr(min_length=11, max_length=13)
    client_name: str

    @validator('whatsapp')
    def validate_whatsapp(cls, v):
        cleaned = v.strip() \
            .replace(" ", "") \
            .replace("-", "") \
            .replace("+", "") \
            .replace("(", "") \
            .replace(")", "")
        
        if not cleaned.isdigit():
            raise ValueError("Número de WhatsApp inválido")
        if len(cleaned) not in (11, 13):
            raise ValueError("Número deve ter 11 (DDD+9 dígitos) ou 13 dígitos (com código país)")
        
        return cleaned

@app.post("/create-document")
async def create_document(payload: NotionPayload):
    try:
        print(f"\n[DEBUG] Iniciando processo para página: {payload.page_id}")
        print(f"[DEBUG] Dados recebidos: {payload.dict()}")

        async with httpx.AsyncClient() as client:
            # 1. Buscar dados do Notion
            print("\n[DEBUG] Buscando dados do Notion...")
            notion_response = await client.get(
                f"https://api.notion.com/v1/pages/{payload.page_id}",
                headers={
                    "Authorization": f"Bearer {NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28"
                }
            )
            notion_response.raise_for_status()
            notion_data = notion_response.json()
            print("[DEBUG] Dados do Notion recebidos com sucesso")

            # 2. Processar PDF
            print("\n[DEBUG] Processando PDF...")
            proposta_pdf = notion_data["properties"]["Proposta PDF"]["files"][0]
            print(f"[DEBUG] Estrutura do PDF: {proposta_pdf.keys()}")

            # Extrair URL do PDF
            if "external" in proposta_pdf:
                pdf_url = proposta_pdf["external"]["url"]
            elif "file" in proposta_pdf:
                pdf_url = proposta_pdf["file"]["url"]
            else:
                raise ValueError("Formato de arquivo não suportado pelo Notion")

            print(f"[DEBUG] URL do PDF: {pdf_url}")

            # Baixar e converter para base64
            pdf_response = await client.get(pdf_url)
            pdf_content = base64.b64encode(pdf_response.content).decode("utf-8")
            print("[DEBUG] PDF convertido para base64")

            # 3. Preparar signatário
            print("\n[DEBUG] Criando payload para ZapSign...")
            signers = [Signer(
                name=payload.client_name,
                email=payload.email,
                phone_number=payload.whatsapp[-11:]  # Mantém últimos 11 dígitos
            ).dict()]

            # 4. Criar documento no ZapSign
            zap_sign_payload = {
                "name": f"Contrato {payload.client_name}",
                "base64_pdf": pdf_content,
                "lang": "pt-br",
                "signers": signers,
                "brand_name": "Corretora 3.0",
                "metadata": [{"key": "notion_page_id", "value": payload.page_id}]
            }

            print(f"[DEBUG] Payload ZapSign: {zap_sign_payload}")

            response = await client.post(
                "https://api.zapsign.com.br/api/v1/docs",
                json=zap_sign_payload,
                headers={
                    "Authorization": f"Bearer {ZAPSIGN_TOKEN}",
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            print("\n[DEBUG] Documento criado com sucesso no ZapSign")

            return {
                "status": "success",
                "document_id": response.json()["open_id"],
                "sign_url": response.json()["signers"][0]["sign_url"]
            }

    except httpx.HTTPStatusError as e:
        error_detail = f"Erro na API externa: {e.response.status_code} - {e.response.text}"
        print(f"\n[ERRO] {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)
    
    except KeyError as e:
        error_detail = f"Campo não encontrado no Notion: {str(e)}"
        print(f"\n[ERRO] {error_detail}")
        raise HTTPException(
            status_code=422,
            detail=error_detail
        )
    
    except Exception as e:
        error_detail = f"Erro interno: {str(e)}"
        print(f"\n[ERRO] {error_detail}")
        raise HTTPException(
            status_code=500,
            detail=error_detail
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)