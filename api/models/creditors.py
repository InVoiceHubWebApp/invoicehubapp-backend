from typing import TYPE_CHECKING, List
from sqlmodel import Field, Relationship, SQLModel
from datetime import datetime
import enum

from api.models.users import UserPublic

if TYPE_CHECKING:
    from api.models.invoices import Invoice
    from api.models.users import User


class CreditorTypeEnum(str, enum.Enum):
    USER = "USER"
    BANK = "BANK"
    PAYMENT_SLIP = "PAYMENT_SLIP"
    PUBLIC_PERSON = "PUBLIC_PERSON"


class Creditor(SQLModel, table=True):
    __tablename__ = "creditor"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    creditor_type: CreditorTypeEnum
    name: str
    due_date: datetime = Field(default=datetime.now())
    limit_value: float | None = None
    enabled: bool = Field(default=True)
    user_as_creditor_id: int | None = Field(foreign_key="user.id")

    created_at: datetime = Field(default=datetime.now())
    updated_at: datetime = Field(default=datetime.now())

    author: "User" = Relationship(
        back_populates="creditors",
        sa_relationship_kwargs={"foreign_keys": "Creditor.user_id"},
    )

    invoices: List["Invoice"] = Relationship(back_populates="responsible_creditor")
    user_as_creditor: "User" = Relationship(
        back_populates="creditors_as_user",
        sa_relationship_kwargs={"foreign_keys": "Creditor.user_as_creditor_id"},
    )


class CreditorBase(SQLModel):
    creditor_type: CreditorTypeEnum
    name: str
    due_date: datetime = Field(default=datetime.now())
    limit_value: float | None = None
    user_as_creditor_id: int | None = None


class CreditorUpdateBase(SQLModel):
    creditor_type: CreditorTypeEnum | None = None
    name: str | None = None
    due_date: datetime | None = None
    limit_value: float | None = None


class CreditorPublic(SQLModel):
    id: int
    creditor_type: CreditorTypeEnum
    name: str
    due_date: datetime
    limit_value: float | None
    enabled: bool
    user_as_creditor_id: int | None
    user_as_creditor: UserPublic | None


class CreditorBasic(SQLModel):
    id: int
    creditor_type: CreditorTypeEnum
    name: str
    user_as_creditor: UserPublic | None
