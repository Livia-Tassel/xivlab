"""bcrypt-based password hashing.

The DEVELOPMENT_GUIDE specified passlib as the wrapper, but passlib 1.7.x
relies on ``bcrypt.__about__.__version__`` which was removed in bcrypt 4.1+
and the project itself is unmaintained. We use the ``bcrypt`` C-binding
directly: same algorithm, same cost (12), forward-compatible.
"""

import bcrypt

# bcrypt's max input is 72 bytes; truncating prevents misleading errors when
# users (or future helpers) pass long passphrases. Truncating at the byte level
# matches what bcrypt itself did silently before 4.1.
_MAX_BYTES = 72
# bcrypt cost factor — 12 matches the passlib default and the spec.
_ROUNDS = 12


def _to_bytes(plain: str) -> bytes:
    encoded = plain.encode("utf-8")
    return encoded[:_MAX_BYTES]


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt at cost 12. Returns ASCII string."""
    salt = bcrypt.gensalt(rounds=_ROUNDS)
    return bcrypt.hashpw(_to_bytes(plain), salt).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time compare. Returns False on any decoding/parsing failure."""
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False
