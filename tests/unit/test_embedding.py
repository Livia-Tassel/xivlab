from unittest.mock import AsyncMock, MagicMock, patch

from app.services.embedding import (
    EMBEDDING_DIM,
    MockBackend,
    OpenAIBackend,
    embed_text,
    from_blob,
    to_blob,
)


async def test_mock_embedding_is_deterministic() -> None:
    a = await embed_text("hello world")
    b = await embed_text("hello world")
    assert a == b
    assert len(a) == EMBEDDING_DIM


async def test_different_text_different_embedding() -> None:
    a = await embed_text("hello world")
    b = await embed_text("goodbye world")
    assert a != b


async def test_mock_embedding_is_l2_normalized() -> None:
    """Cosine similarity downstream assumes unit-length vectors."""
    vec = await MockBackend.embed("anything")
    norm = sum(f * f for f in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-6


async def test_mock_embedding_handles_empty_string() -> None:
    """Empty input still yields a valid 1536-d unit vector (no NaN/zero-div)."""
    vec = await embed_text("")
    assert len(vec) == EMBEDDING_DIM
    norm = sum(f * f for f in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_to_blob_produces_correct_byte_size() -> None:
    """sqlite-vec expects 1536 * 4 = 6144 bytes (float32 little-endian)."""
    vec = [0.1] * EMBEDDING_DIM
    blob = to_blob(vec)
    assert isinstance(blob, bytes)
    assert len(blob) == EMBEDDING_DIM * 4


def test_blob_roundtrip_preserves_values() -> None:
    """to_blob / from_blob is identity within float32 precision."""
    vec = [i / 1000.0 - 0.5 for i in range(EMBEDDING_DIM)]
    decoded = from_blob(to_blob(vec))
    assert len(decoded) == EMBEDDING_DIM
    for original, restored in zip(vec, decoded, strict=True):
        assert abs(original - restored) < 1e-6


async def test_openai_backend_calls_create_with_settings() -> None:
    """OpenAIBackend should pass model+input to AsyncOpenAI client and return the embedding."""
    fake_embedding = [0.0] * EMBEDDING_DIM
    fake_response = MagicMock()
    fake_response.data = [MagicMock(embedding=fake_embedding)]

    fake_client = MagicMock()
    fake_client.embeddings.create = AsyncMock(return_value=fake_response)

    with patch("openai.AsyncOpenAI", return_value=fake_client) as ctor:
        result = await OpenAIBackend.embed("a paper title")

    assert result == fake_embedding
    ctor.assert_called_once()
    fake_client.embeddings.create.assert_awaited_once()
    call_kwargs = fake_client.embeddings.create.await_args.kwargs
    assert call_kwargs["input"] == "a paper title"
    # model is read from settings.embedding_model (defaults to text-embedding-3-small)
    assert call_kwargs["model"] == "text-embedding-3-small"
