"""Provider-agnostic embedding service.

Backend selection is driven by ``settings.embedding_provider``:
- ``"mock"`` (default in tests/dev) — deterministic SHA256-derived
  L2-normalized 1536-d vector. Useful in tests because identical input
  always produces identical output without any external dependency.
- ``"openai"`` — calls ``client.embeddings.create`` via the official
  AsyncOpenAI client. The import is lazy so test envs without an API
  key don't pay for the SDK at import time.

Vectors are 1536-d float32 (matching ``text-embedding-3-small``). Use
:func:`to_blob` / :func:`from_blob` to (de)serialize for the
``task_embeddings.embedding`` and ``paper_vectors`` BLOB columns —
sqlite-vec expects little-endian float32 packed contiguously.
"""

import hashlib
import struct

from app.config import get_settings

EMBEDDING_DIM: int = 1536


class MockBackend:
    """Deterministic embedding derived from SHA256 of the input.

    Identical input → identical 1536-d unit vector across processes,
    so tests can assert exact equality without seeding anything.
    """

    @staticmethod
    async def embed(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        floats: list[float] = []
        for i in range(EMBEDDING_DIM):
            chunk_idx = (i * 4) % 32
            chunk = digest[chunk_idx : chunk_idx + 4]
            if len(chunk) < 4:
                chunk = (chunk + digest[:4])[:4]
            (val,) = struct.unpack("<I", chunk)
            floats.append(((val + i * 17) % 10000) / 10000.0 - 0.5)
        norm = sum(f * f for f in floats) ** 0.5 or 1.0
        return [f / norm for f in floats]


class OpenAIBackend:
    @staticmethod
    async def embed(text: str) -> list[float]:
        from openai import AsyncOpenAI

        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        r = await client.embeddings.create(
            model=settings.embedding_model,
            input=text,
        )
        return r.data[0].embedding


def get_backend() -> type[MockBackend] | type[OpenAIBackend]:
    if get_settings().embedding_provider == "openai":
        return OpenAIBackend
    return MockBackend


async def embed_text(text: str) -> list[float]:
    return await get_backend().embed(text)


def to_blob(vec: list[float]) -> bytes:
    """Pack a vector as little-endian float32 for sqlite-vec storage."""
    return struct.pack(f"<{len(vec)}f", *vec)


def from_blob(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))
