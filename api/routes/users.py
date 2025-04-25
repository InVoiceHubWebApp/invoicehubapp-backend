from http import HTTPStatus
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from api.config.database import get_db
from api.config.security import get_password_hash
from api.models.users import UserPublic, User, UserBase
from api.utils.auth import get_current_user

router = APIRouter()


@router.get("", status_code=HTTPStatus.OK, response_model=List[UserPublic])
async def get_users(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    users = db.scalars(select(User).where(User.id != user.id))
    return users


@router.get("/me", status_code=HTTPStatus.OK, response_model=UserPublic)
async def get_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@router.get(
    "/search",
    status_code=HTTPStatus.OK,
    response_model=List[UserPublic],
)
async def get_users_by_search(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    search: Annotated[str, Query()],
):
    if len(search) > 1:
        query = select(User).where(
            (User.username.ilike(f"%{search}%")) & (User.id != current_user.id)
        )
        result = db.exec(query).all()
        return result
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail="Search string must be at least 2 characters long",
    )


@router.post("", status_code=HTTPStatus.CREATED, response_model=UserPublic)
async def create_user(db: Annotated[Session, Depends(get_db)], user: UserBase):
    db_user = db.scalar(
        select(User).where(
            (User.email == user.email) | (User.username == user.username)
        )
    )
    if db_user:
        if db_user.username == user.username:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST, detail="Username already exists"
            )
        elif db_user.email == user.email:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST, detail="Email already exists"
            )

    new_user = User(
        name=user.name,
        lastname=user.lastname,
        email=user.email,
        username=user.username,
        password=get_password_hash(user.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user
