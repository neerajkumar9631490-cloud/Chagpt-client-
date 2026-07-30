# ChatGPT Proxy API

Self-hosted ChatGPT API proxy. Deploy to Railway in one click.

## Deploy

1. Push this repo to GitHub
2. Go to [railway.com](https://railway.com) → New Project → Deploy from GitHub
3. (Optional) Add env var `API_KEY` for authentication
4. Deploy. Grab your public URL.

## Usage

### Streaming (SSE)

```bash
curl -N https://your-app.up.railway.app/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"message": "Hello!", "stream": true}'
```

### Non-streaming

```bash
curl https://your-app.up.railway.app/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "stream": false}'
```

### OpenAI-compatible (drop-in for openai SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://your-app.up.railway.app/v1",
    api_key="YOUR_API_KEY",  # or "sk-anything" if no key set
)

resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hi"}],
    stream=True,
)
for chunk in resp:
    print(chunk.choices[0].delta.content or "", end="")
```

### Reset conversation

```bash
curl -X POST https://your-app.up.railway.app/v1/reset
```

## Env Vars

| Variable  | Required | Description              |
|-----------|----------|--------------------------|
| `API_KEY` | No       | Bearer token for auth    |
| `PORT`    | No       | Server port (default 8000, Railway sets this) |
