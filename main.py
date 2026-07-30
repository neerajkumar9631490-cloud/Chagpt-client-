import os
import json
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from chatgpt_client import ChatGPTClient

# ─── App State ────────────────────────────────────────────────────────────────

client: Optional[ChatGPTClient] = None
client_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = ChatGPTClient()
    await client.init()
    print("[✓] ChatGPT client initialized")
    yield
    print("[✗] Shutting down")


app = FastAPI(title="ChatGPT Proxy API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Auth (optional) ─────────────────────────────────────────────────────────

API_KEY = os.environ.get("API_KEY", "")


def verify_key(request: Request):
    if not API_KEY:
        return
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        auth = auth[7:]
    if auth != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ─── Models ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    stream: bool = True
    reset: bool = False


class ChatResponse(BaseModel):
    response: str
    conversation_id: Optional[str] = None


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "model": "chatgpt-auto"}


@app.post("/v1/chat")
async def chat(req: ChatRequest, request: Request):
    verify_key(request)

    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    async with client_lock:
        if req.reset:
            client.reset()

        if req.stream:
            return StreamingResponse(
                _stream_response(req.message),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            try:
                full_text = ""
                async for chunk in client.chat(req.message):
                    full_text += chunk
                return ChatResponse(
                    response=full_text,
                    conversation_id=client.conversation_id,
                )
            except Exception as e:
                raise HTTPException(status_code=502, detail=str(e))


async def _stream_response(message: str):
    try:
        async for chunk in client.chat(message):
            data = json.dumps({"content": chunk})
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        error = json.dumps({"error": str(e)})
        yield f"data: {error}\n\n"
        yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def openai_compat(request: Request):
    """OpenAI-compatible endpoint for drop-in replacement."""
    verify_key(request)
    body = await request.json()

    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="No messages")

    # Combine all messages into one prompt
    prompt = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
    )
    stream = body.get("stream", False)

    async with client_lock:
        if stream:
            return StreamingResponse(
                _openai_stream(prompt),
                media_type="text/event-stream",
            )
        else:
            full_text = ""
            async for chunk in client.chat(prompt):
                full_text += chunk
            return JSONResponse({
                "id": "chatcmpl-proxy",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": full_text},
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            })


async def _openai_stream(prompt: str):
    try:
        async for chunk in client.chat(prompt):
            data = json.dumps({
                "id": "chatcmpl-proxy",
                "object": "chat.completion.chunk",
                "choices": [{
                    "index": 0,
                    "delta": {"content": chunk},
                    "finish_reason": None,
                }],
            })
            yield f"data: {data}\n\n"
        final = json.dumps({
            "id": "chatcmpl-proxy",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        })
        yield f"data: {final}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"


@app.post("/v1/reset")
async def reset(request: Request):
    verify_key(request)
    async with client_lock:
        client.reset()
    return {"status": "reset", "message": "Conversation cleared"}


# ─── Entry ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
