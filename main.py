from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from chatgpt_client import ChatGPTClient
import traceback

app = FastAPI(title="ChatGPT API", description="Unofficial ChatGPT API wrapper")

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Send a message to ChatGPT and get the full response.
    Each request starts a fresh conversation.
    """
    client = ChatGPTClient()
    try:
        # Initialize client (gets cookies, build version)
        await client.init()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Init failed: {str(e)}")

    full_response = ""
    try:
        # Stream the response and accumulate
        async for chunk in client.chat(request.message):
            full_response += chunk
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")
    finally:
        # Optional: reset client state if you want to reuse,
        # but we create a new client per request anyway.
        pass

    return {"response": full_response}

# Health check (optional)
@app.get("/health")
async def health():
    return {"status": "ok"}
