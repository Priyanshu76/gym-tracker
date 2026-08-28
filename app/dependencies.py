import uuid
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models.session import Session as SessionModel
from app.models.user import User
from app.services.security import decode_access_token

COOKIE_NAME = "access_token"


def get_current_user(
    access_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: DBSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired session — please log in again",
    )

    if not access_token:
        raise unauthorized

    payload = decode_access_token(access_token)
    if not payload:
        raise unauthorized

    jti = payload.get("jti")
    user_id = payload.get("sub")
    if not jti or not user_id:
        raise unauthorized

    # Checking the DB (not just trusting the JWT signature) is what lets a
    # password reset or manual revoke actually invalidate a session early —
    # a pure-JWT approach can't do this without a token blocklist anyway,
    # so we just keep sessions in the DB from the start.
    session = (
        db.query(SessionModel)
        .filter(SessionModel.token_jti == jti, SessionModel.revoked.is_(False))
        .first()
    )
    if not session:
        raise unauthorized

    if session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise unauthorized

    user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if not user:
        raise unauthorized

    return user
