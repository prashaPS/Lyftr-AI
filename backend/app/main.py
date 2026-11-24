import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

from .database import Database
from .llm import LLMManager
from .models import ChatRequest, ChatResponse, HealthResponse

# ── Environment ───────────────────────────────────────────────────────────────
_raw_keys = os.getenv("LLM_API_KEYS", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ENABLE_FAILURE_SIMULATION = (
    os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
)

# Build key pool: key_1, key_2, ...
key_pool = []
for i, raw in enumerate(_raw_keys.split(","), start=1):
    v = raw.strip()
    if v:
        key_pool.append({"id": f"key_{i}", "value": v})

allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# ── Singletons ────────────────────────────────────────────────────────────────
db = Database(DATABASE_URL)
llm = LLMManager(key_pool)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Lyftr AI Chatbot API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if "*" not in allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    """Liveness + readiness check."""
    db.check_health()
    return HealthResponse(
        status="ok",
        keys_configured=len(key_pool),
        cache_enabled=llm.cache_enabled,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None),
):
    """Main chat endpoint with key failover and response caching."""

    # Parse X-Simulate-Failure header (only when flag is on)
    simulated: dict = {}
    if ENABLE_FAILURE_SIMULATION and x_simulate_failure:
        for pair in x_simulate_failure.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, s = pair.split("=", 1)
                try:
                    simulated[k.strip()] = int(s.strip())
                except ValueError:
                    pass

    # Load session history
    history = db.get_messages(body.session_id)

    # Build LLM messages
    messages = []
    if body.system_prompt:
        messages.append({"role": "system", "content": body.system_prompt})
    messages.extend(history)
    messages.append({"role": "user", "content": body.message})

    # Call LLM (raises HTTPException on failure)
    result = await llm.chat(messages, simulated)

    # Persist to SQLite only on success
    db.add_message(body.session_id, "user", body.message)
    db.add_message(
        body.session_id,
        "assistant",
        result["reply"],
        {
            "resolution_source": result["resolution_source"],
            "model": result["model"],
            "latency_ms": result["latency_ms"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "key_id": result["key_id"],
            "fallback_attempts": result["fallback_attempts"],
        },
    )

    return ChatResponse(
        session_id=body.session_id,
        reply=result["reply"],
        metadata={
            "resolution_source": result["resolution_source"],
            "model": result["model"],
            "latency_ms": result["latency_ms"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "key_id": result["key_id"],
            "fallback_attempts": result["fallback_attempts"],
        },
    )


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Return stored history for a session."""
    if not db.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    messages = db.get_messages_with_metadata(session_id)
    return {"session_id": session_id, "messages": messages}
