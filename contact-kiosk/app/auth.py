"""
Minimal admin authentication.

This app is designed for a trusted LAN only (see README). Admin auth is a
single shared PIN rather than per-user accounts, which is appropriate for a
small office kiosk but should NOT be exposed to the open internet.

The PIN is hashed with a salted SHA-256 (stdlib only, no extra dependency)
and stored in /app/data/admin_pin.txt on first run. A successful login sets
a signed, time-limited cookie via itsdangerous so the admin doesn't have to
re-enter the PIN on every request.
"""
import hashlib
import secrets
from pathlib import Path

from fastapi import Cookie, HTTPException, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

DATA_DIR = Path(__file__).parent / "data"
PIN_FILE = DATA_DIR / "admin_pin.txt"
SECRET_FILE = DATA_DIR / "session_secret.txt"

SESSION_COOKIE_NAME = "kiosk_admin_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 8  # 8 hour admin session

DEFAULT_PIN = "1234"  # change immediately on first deployment - see README


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()


def _get_or_create_secret() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text().strip()
    secret = secrets.token_hex(32)
    SECRET_FILE.write_text(secret)
    return secret


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_get_or_create_secret(), salt="admin-session")


def ensure_pin_file_exists() -> None:
    """Create a default PIN file on first run so the app boots cleanly."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PIN_FILE.exists():
        salt = secrets.token_hex(8)
        PIN_FILE.write_text(f"{salt}:{_hash_pin(DEFAULT_PIN, salt)}")


def verify_pin(pin: str) -> bool:
    if not PIN_FILE.exists():
        ensure_pin_file_exists()
    salt, stored_hash = PIN_FILE.read_text().strip().split(":", 1)
    return secrets.compare_digest(_hash_pin(pin, salt), stored_hash)


def set_pin(new_pin: str) -> None:
    salt = secrets.token_hex(8)
    PIN_FILE.write_text(f"{salt}:{_hash_pin(new_pin, salt)}")


def create_session_token() -> str:
    return _serializer().dumps({"role": "admin"})


def require_admin(kiosk_admin_session: str | None = Cookie(default=None)) -> None:
    """FastAPI dependency: raises 401 unless a valid admin session cookie is present."""
    if not kiosk_admin_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    try:
        _serializer().loads(kiosk_admin_session, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
