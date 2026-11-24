from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=4000)
    system_prompt: Optional[str] = None

    @field_validator("message")
    @classmethod
    def message_stripped_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be empty after trimming whitespace")
        if len(v) > 4000:
            raise ValueError("message must be at most 4000 characters")
        return v


class Metadata(BaseModel):
    resolution_source: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str]
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: Metadata


class HealthResponse(BaseModel):
    status: str
    keys_configured: int
    cache_enabled: bool
