import secrets


def random_token(nbytes: int = 32) -> str:
    """Cryptographically random URL-safe token (default 32 bytes ≈ 256 bits of entropy)."""
    return secrets.token_urlsafe(nbytes)
