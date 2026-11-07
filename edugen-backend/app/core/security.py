"""Mật khẩu (PBKDF2-SHA256, thư viện chuẩn), access token JWT và refresh token.

Access token chứa id user và dấu vân tay mật khẩu; quyền (role, trường, khóa tài khoản) đọc lại
từ DB mỗi request nên khóa tài khoản hay đổi mật khẩu có hiệu lực ngay. Refresh token là chuỗi ngẫu nhiên, DB chỉ lưu hash.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def hash_password(password: str) -> str:
    iterations = settings.password_hash_iterations
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        scheme, iterations, salt, digest = hashed.split("$")
        salt_bytes = base64.urlsafe_b64decode(salt + "=" * (-len(salt) % 4))
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, int(iterations))
    return hmac.compare_digest(_b64(actual), digest)


def password_needs_rehash(hashed: str) -> bool:
    """Hash tạo với số vòng thấp hơn cấu hình hiện tại → băm lại khi user đăng nhập đúng."""
    try:
        return int(hashed.split("$")[1]) < settings.password_hash_iterations
    except (IndexError, ValueError):
        return True


def password_fingerprint(password_hash: str) -> str:
    """Dấu vân tay của mật khẩu hiện tại, nhúng vào access token: đổi mật khẩu là token cũ hết hiệu lực."""
    return hmac.new(settings.jwt_secret.encode(), password_hash.encode(), hashlib.sha256).hexdigest()[:16]


def create_access_token(user_id: str, password_hash: str | None = None) -> str:
    now = datetime.now(UTC)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)}
    if password_hash is not None:
        payload["pwv"] = password_fingerprint(password_hash)
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_claims(token: str) -> dict | None:
    """Claims của token, hoặc None nếu sai chữ ký/hết hạn/thiếu exp hoặc sub."""
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]}
        )
    except jwt.PyJWTError:
        return None


def decode_access_token(token: str) -> str | None:
    """Trả id user, hoặc None nếu token không hợp lệ."""
    claims = decode_access_claims(token)
    return claims["sub"] if claims else None


def new_refresh_token() -> tuple[str, str, datetime]:
    """(token gửi client, hash lưu DB, thời điểm hết hạn)."""
    token = secrets.token_urlsafe(32)
    return token, hash_refresh_token(token), datetime.now(UTC) + timedelta(days=settings.refresh_token_days)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
