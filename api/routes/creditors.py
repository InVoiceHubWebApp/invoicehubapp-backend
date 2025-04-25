from http import HTTPStatus
import math
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func
from api.config.database import get_db
from api.models.creditors import (
    Creditor,
    CreditorBase,
    CreditorBasic,
    CreditorPublic,
    CreditorUpdateBase,
)

from api.models.pagination import Page
from api.models.users import User
from api.utils.auth import get_current_user

router = APIRouter()


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    response_model=Creditor,
)
def create_creditor(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    creditor: CreditorBase,
):
    if creditor.creditor_type != "USER" and creditor.user_as_creditor_id is not None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="A user id should only be provided if the entity is of type USER",
        )

    if creditor.creditor_type == "USER" and creditor.user_as_creditor_id is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="If your entity is of type USER you must provide a user id.",
        )

    if (
        creditor.user_as_creditor_id is not None
        and creditor.user_as_creditor_id == user.id
    ):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="You can't reference yourself"
        )

    if creditor.user_as_creditor_id is not None:
        query = select(User).where((User.id == creditor.user_as_creditor_id))
        user_as_creditor = db.scalar(query)
        if user_as_creditor == None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="User used as creditor was not found",
            )

    if creditor.creditor_type != "USER" and creditor.user_as_creditor_id is not None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="A user id should only be provided if the entity is of type USER",
        )

    new_creditor = Creditor(
        user_id=user.id,
        creditor_type=creditor.creditor_type,
        name=creditor.name,
        due_date=creditor.due_date,
        limit_value=creditor.limit_value,
        user_as_creditor_id=creditor.user_as_creditor_id,
    )

    db.add(new_creditor)
    db.commit()
    db.refresh(new_creditor)

    return new_creditor


@router.get(
    "",
    status_code=HTTPStatus.OK,
    response_model=Page[CreditorPublic],
)
def get_creditors(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(gt=0)] = 25,
):
    offset = page * size
    query = select(Creditor).where((Creditor.user_id == user.id) & (Creditor.enabled))
    creditors = db.scalars(query.offset(offset).limit(size))
    total = db.scalar(query.with_only_columns(func.count(Creditor.id)))
    pages = math.ceil(total / size)

    return {
        "items": creditors,
        "page": page,
        "size": size,
        "pages": pages,
        "total": total,
    }


@router.get(
    "/list",
    status_code=HTTPStatus.OK,
    response_model=List[CreditorBasic],
)
def get_creditors_list(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    query = select(Creditor).where((Creditor.user_id == user.id) & (Creditor.enabled))
    creditors = db.exec(query).all()
    return creditors


@router.delete("/{id}", status_code=HTTPStatus.NO_CONTENT)
def delete_creditor(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    id: int,
):
    creditor = db.scalar(select(Creditor).where((Creditor.id == id)))
    if creditor:
        if creditor.author.id != user.id:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="You do not have permission to delete this item.",
            )
        if not creditor.enabled:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT, detail="Item is already disabled."
            )
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found")

    creditor.sqlmodel_update({"enabled": False})
    db.add(creditor)
    db.commit()
    db.refresh(creditor)


@router.patch(
    "/{id}",
    status_code=HTTPStatus.OK,
    response_model=Creditor,
)
def update_creditor(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    id: int,
    creditor: CreditorUpdateBase,
):
    db_creditor = db.scalar(select(Creditor).where(Creditor.id == id))
    if db_creditor is not None:
        if db_creditor.author.id != user.id:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="You do not have permission to update this item.",
            )
        if not db_creditor.enabled:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT, detail="Item is disabled."
            )
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found")

    data = creditor.model_dump(exclude_unset=True)
    db_creditor.sqlmodel_update(data)
    db.add(db_creditor)
    db.commit()
    db.refresh(db_creditor)
    return db_creditor
