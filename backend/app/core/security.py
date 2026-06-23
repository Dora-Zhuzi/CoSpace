from datetime import datetime, timedelta, timezone
import bcrypt
from jose import JWTError, jwt
from fastapi import HTTPException, status
from app.core.config import settings


def _encode(password: str) -> bytes:
    # bcrypt 仅取前 72 字节，超长密码先截断避免报错
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_encode(plain), hashed.encode())


def create_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
    return jwt.encode(
        {"sub": user_id, "email": email, "exp": expire},
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的 token"
        )
