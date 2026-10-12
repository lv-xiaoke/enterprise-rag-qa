import hashlib
import secrets
import time
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import HTTPException, Request
from backend.models import AuthSession, User

hasher = PasswordHasher()


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerifyMismatchError, VerificationError):
        return False


def require_csrf(request: Request):
    origin = request.headers.get('origin')
    cookie = request.cookies.get('csrf_token', '')
    header = request.headers.get('x-csrf-token', '')
    if origin != request.app.state.settings.app_origin or not cookie or not secrets.compare_digest(cookie, header):
        raise HTTPException(403, '请求来源或 CSRF 校验失败')


def current_user(request: Request):
    credential = request.cookies.get('session', '')
    with request.app.state.database.session() as db:
        session = db.get(AuthSession, token_hash(credential)) if credential else None
        if not session or session.revoked or session.expires_at <= time.time():
            raise HTTPException(401, '请先登录')
        user = db.get(User, session.user_id)
        if not user:
            raise HTTPException(401, '登录已失效')
        return user


def administrator(request: Request):
    user = current_user(request)
    if user.role != 'admin':
        raise HTTPException(403, '需要管理员权限')
    return user


def public_user(user):
    return {key: getattr(user, key) for key in ('id', 'username', 'name', 'role', 'employee_id')}
