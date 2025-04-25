from typing import TYPE_CHECKING, List
from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from api.models.creditors import Creditor
    from api.models.invoices import Invoice


class IncomeSource(SQLModel, table=True):
    __tablename__ = "income_source"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    value: float


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: int = Field(primary_key=True)
    name: str
    lastname: str
    email: EmailStr = Field(nullable=False, unique=True)
    username: str = Field(nullable=False, unique=True)
    password: str
    spending_limit: float | None = Field(default=None)
    reserve_fund: float | None = Field(default=None)

    invoices: List["Invoice"] = Relationship(back_populates="author")
    creditors: List["Creditor"] = Relationship(
        back_populates="author",
        sa_relationship_kwargs={"foreign_keys": "Creditor.user_id"},
    )
    creditors_as_user: List["Creditor"] = Relationship(
        back_populates="user_as_creditor",
        sa_relationship_kwargs={"foreign_keys": "Creditor.user_as_creditor_id"},
    )


class UserBase(SQLModel):
    name: str
    lastname: str
    email: EmailStr
    username: str
    password: str


class UserPublic(SQLModel):
    id: int
    name: str
    lastname: str
    username: str
    email: EmailStr
