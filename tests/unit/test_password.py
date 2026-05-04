from app.services.password import hash_password, verify_password


def test_hash_then_verify_succeeds() -> None:
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h) is True


def test_verify_wrong_password_fails() -> None:
    h = hash_password("secret123")
    assert verify_password("wrong", h) is False


def test_hash_password_produces_different_hashes_each_call() -> None:
    """bcrypt salts every hash, so two calls with the same plaintext differ."""
    h1 = hash_password("secret123")
    h2 = hash_password("secret123")
    assert h1 != h2
    assert verify_password("secret123", h1) is True
    assert verify_password("secret123", h2) is True
