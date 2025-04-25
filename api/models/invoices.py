from typing import List
from sqlmodel import Field, Relationship, SQLModel
from datetime import datetime
import enum

from api.models.creditors import Creditor, CreditorBasic
from api.models.users import User


class PaymentStatusEnum(str, enum.Enum):
    paid = "PAID"
    pending = "PENDING"
    overdue = "OVERDUE"


class PaymentTypeEnum(str, enum.Enum):
    installment = "INSTALLMENT"
    cash = "CASH"
    fixed = "FIXED"


class Invoice(SQLModel, table=True):
    __tablename__ = "invoice"

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    creditor_id: int | None = Field(default=None, foreign_key="creditor.id")
    purchase_date: datetime = Field(default=datetime.now())
    title: str
    value: float
    installments: int | None = None
    payment_type: PaymentTypeEnum
    paid_status: PaymentStatusEnum = Field(default=PaymentStatusEnum.pending)
    enabled: bool = Field(default=True)
    invoice_parent_id: int | None = Field(default=None, foreign_key="invoice.id")

    created_at: datetime = Field(default=datetime.now())
    updated_at: datetime = Field(default=datetime.now())

    author: "User" = Relationship(back_populates="invoices")

    parent_invoice: "Invoice" = Relationship(
        sa_relationship_kwargs={"remote_side": "Invoice.id"},
        back_populates="external_payments",
    )
    external_payments: List["Invoice"] = Relationship(back_populates="parent_invoice")
    responsible_creditor: "Creditor" = Relationship(back_populates="invoices")


class ExternalPaymentCreditor(SQLModel):
    creditor_id: int
    value: float


class InvoiceBase(SQLModel):
    creditor_id: int | None = None
    purchase_date: datetime = Field(default=datetime.now())
    title: str
    value: float
    installments: int | None = None
    payment_type: PaymentTypeEnum
    paid_status: PaymentStatusEnum = Field(default=PaymentStatusEnum.pending)
    external_payments: List["ExternalPaymentCreditor"] = Field(default=[])


class InvoiceBasic(SQLModel):
    id: int
    purchase_date: datetime
    title: str
    date: datetime


class ExternalPaymentCreditorUpdate(SQLModel):
    creditor_id: int | None = None
    value: float | None = None
    id: int | None = None


class InvoiceUpdateBase(SQLModel):
    creditor_id: int | None = None
    purchase_date: datetime | None = None
    title: str | None = None
    value: float | None = None
    installments: int | None = None
    payment_type: PaymentTypeEnum | None = None
    paid_status: PaymentStatusEnum | None = None
    external_payments: List["ExternalPaymentCreditorUpdate"] | None = None


class InvoicePaidBase(SQLModel):
    ids: List[int] = []


class ExternalPayment(SQLModel):
    responsible_creditor: CreditorBasic
    value: float
    id: int


class InvoicePublic(SQLModel):
    id: int
    creditor_id: int
    purchase_date: datetime
    title: str
    value: float
    installments: int | None = Field(default=None)
    installment_value: float | None = Field(default=None)
    installment_paid: int
    last_payment_date: datetime
    payment_type: PaymentTypeEnum
    paid_status: PaymentStatusEnum = Field(default=PaymentStatusEnum.pending)

    external_payments: List[ExternalPayment] | None
    responsible_creditor: CreditorBasic


class InvoiceStatsByCreditor(SQLModel):
    id: int
    name: str
    amount_receivable: float = Field(default=0)
    amount_payable: float = Field(default=0)
    total_value: float = Field(default=0)


class InvoiceStatsByMonth(SQLModel):
    date: datetime
    amount: float


class InvoiceStatsByWeek(SQLModel):
    day_of_week: int
    amount: float


class InvoiceStatsByPaymentType(SQLModel):
    payment_type: str
    amount: float
