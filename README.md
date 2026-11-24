# Lyftr AI Chatbot

LLM Chatbot with **key failover**, **response caching**, and **multi-turn conversation** — built with FastAPI + LiteLLM + React + SQLite.

---

## 1. Live URLs

| Service  | URL |
|----------|-----|
| Frontend | `https://lyftr-frontend.vercel.app` *(update after deploy)* |
| Backend  | `https://lyftr-backend.onrender.com` *(update after deploy)* |

---

## 2. Run Locally

### With Docker (recommended)

```bash
# 1. Copy and fill in your keys
cp .env.example .env
# Edit .env: set LLM_API_KEYS=AIzaSy...,AIzaSy...

# 2. Start both services
make up

# Frontend → http://localhost:3000
# Backend  → http://localhost:8000
# Health   → http://localhost:8000/health
```

### Without Docker

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

export LLM_API_KEYS="AIzaSy...,AIzaSy..."
export DATABASE_URL="sqlite:///./app.db"
export ALLOWED_ORIGINS="http://localhost:3000"
export ENABLE_FAILURE_SIMULATION="true"

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**
```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
# → http://localhost:3000
```

**Run backend tests:**
```bash
cd backend
pip install pytest pytest-asyncio anyio httpx
pytest tests/ -v
```

---

## 3. Design Decisions

### Key Fallback
The backend maintains an **ordered key pool** (`key_1`, `key_2`, …) parsed from `LLM_API_KEYS`. On each `/chat` request, the `LLMManager` iterates the pool and calls `litellm.acompletion` with that key's value. If the call raises a `429`, `500`, `502`, or `503`, the attempt is counted as a `fallback_attempt` and the next key is tried. If every key fails, a `503` with `{"detail": "all providers unavailable"}` is returned — no stack trace ever reaches the client. The `X-Simulate-Failure` header triggers the same path without touching real quota (only when `ENABLE_FAILURE_SIMULATION=true`).

### Caching
LiteLLM's built-in disk cache (`litellm.cache = Cache(type="disk")`) is enabled globally. Each `acompletion` call passes `caching=True`. When LiteLLM serves a cache hit, `response._hidden_params["cache_hit"]` is `True` and we return `resolution_source: LLM_CACHE`, `key_id: null`, and the stored token counts. We also maintain a fast in-memory dict (`_mem_cache`) for sub-millisecond repeated lookups in the same process. Cache key = SHA-256 of `{model, messages}` JSON.

### SQLite Session Storage
Every successful exchange is written to SQLite after the LLM responds — if the LLM fails, nothing is persisted. The `session_id` is client-generated (UUID prefix) and determines the conversation thread. History is loaded from SQLite on every `/chat` request and prepended to the LLM message list, giving the model full multi-turn context. The database file lives at `/data/app.db` (Docker volume), surviving container restarts.

---

## 4. Verification

### Cache hits
```bash
# First call → LIVE_INFERENCE
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo","message":"What is 2+2?"}'

# Same message in a new session → LLM_CACHE (faster latency)
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo2","message":"What is 2+2?"}'
```

### Failover with X-Simulate-Failure
```bash
# key_1 fails → key_2 answers (key_id = key_2, fallback_attempts = 1)
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: key_1=429' \
  -d '{"session_id":"fail1","message":"Hello"}'

# All keys fail → 503
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: *=429' \
  -d '{"session_id":"fail2","message":"Hello"}'
```

### Per-message token usage
Every `/chat` response includes `input_tokens` and `output_tokens` in `metadata`. Each is for **that request only** (system prompt + history + new message → reply), never a running total.

### Session history
```bash
curl http://localhost:8000/sessions/demo/messages
```

---

## 5. Setup Used

- **Editor:** VS Code + Antigravity AI assistant
- **AI tools:** Google Deepmind Antigravity (code generation and architecture guidance)
- **Deployment:** Render (backend), Vercel (frontend)
- **Key management:** Google AI Studio (Gemini API)

---

## 6. Bonus Features

- **System prompt input:** An optional field lets users set a per-session system prompt from the UI (maps to the `system_prompt` field in `/chat`).
- **Fallback attempt badge:** The UI shows an amber `⚠ N fallbacks` chip when a failover occurred, making resilience visible.
- **Cache vs live color coding:** `LLM_CACHE` replies show in green, `LIVE_INFERENCE` in indigo — instantly readable.
- **Auto-resize textarea:** The input grows up to 4 lines before scrolling.
- **Health indicator:** A live dot in the header shows whether the backend is reachable.
