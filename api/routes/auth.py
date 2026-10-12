import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from backend.auth import current_user, public_user, require_csrf, token_hash, verify_password
from backend.models import AuthSession, User
from api.schemas import LoginRequest

router = APIRouter(prefix='/auth', tags=['登录'])


@router.get('/csrf')
def csrf(request: Request, response: Response):
    token = request.cookies.get('csrf_token') or secrets.token_urlsafe(32)
    response.set_cookie('csrf_token', token, httponly=True, samesite='lax',
                        secure=request.app.state.settings.cookie_secure, max_age=86400)
    return {'csrf_token': token}


@router.post('/login', dependencies=[Depends(require_csrf)])
def login(body: LoginRequest, request: Request, response: Response):
    # Bounded per-process rate limiting protects password hashing on the single-worker MVP.
    now = time.time()
    host = request.client.host if request.client else 'unknown'
    attempts = request.app.state.login_attempts
    for key in list(attempts):
        attempts[key] = [stamp for stamp in attempts[key] if stamp > now - 60]
        if not attempts[key]:
            del attempts[key]
    recent = attempts.setdefault(host, [])
    if len(recent) >= 20:
        raise HTTPException(429, '登录尝试过于频繁，请稍后重试')
    recent.append(now)
    with request.app.state.database.session() as db:
        user = db.scalar(select(User).where(User.username == body.username))
        encoded = user.password_hash if user else request.app.state.dummy_password_hash
        if not verify_password(encoded, body.password) or not user:
            raise HTTPException(401, '账号或密码错误')
        credential = secrets.token_urlsafe(32)
        old = request.cookies.get('session')
        if old:
            previous = db.get(AuthSession, token_hash(old))
            if previous:
                previous.revoked = True
        hours = request.app.state.settings.session_hours
        db.add(AuthSession(token_hash=token_hash(credential), user_id=user.id,
                           expires_at=now + hours * 3600))
        db.commit()
        response.set_cookie('session', credential, httponly=True, samesite='lax',
                            secure=request.app.state.settings.cookie_secure, max_age=hours * 3600)
        return public_user(user)


@router.get('/me')
def me(user=Depends(current_user)):
    return public_user(user)


@router.post('/logout', dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response, user=Depends(current_user)):
    with request.app.state.database.session() as db:
        session = db.get(AuthSession, token_hash(request.cookies['session']))
        session.revoked = True
        db.commit()
    response.delete_cookie('session')
    return {'ok': True}
