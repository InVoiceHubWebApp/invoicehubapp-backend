from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Annotated
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Security
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from jwt import encode, decode
from jwt.exceptions import PyJWTError
from api.config.database import get_db
from api.config.settings import get_env
from sqlmodel import Session, select

from api.models.users import User

env = get_env()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
api_key_scheme = APIKeyHeader(name="X-KEY")


def create_access_token(data: dict):
    to_encode = data.copy()

    expire = datetime.now(tz=ZoneInfo("UTC")) + timedelta(
        minutes=int(env.TOKEN_ACCESS_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    encode_jwt = encode(to_encode, env.TOKEN_SECRET, algorithm=env.TOKEN_ALGORITHM)
    return encode_jwt


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
):
    credentials_exception = HTTPException(
        status_code=HTTPStatus.UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode(token, env.TOKEN_SECRET, algorithms=[env.TOKEN_ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except PyJWTError:
        raise credentials_exception

    user = db.scalar(select(User).where((User.username == username)))

    if not user:
        raise credentials_exception
    return user


async def get_api_key(api_key: str = Security(api_key_scheme)):
    if api_key == env.API_KEY:
        return api_key
    else:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Missing or invalid API key",
        )
