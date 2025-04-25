from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import INTEGER, text, literal
from sqlmodel import Session, select, func, case
from sqlalchemy.orm.attributes import InstrumentedAttribute

from api.config.database import get_db
from api.models.creditors import Creditor
from api.models.invoices import ExternalPaymentCreditorUpdate, Invoice, InvoiceBase
from api.models.users import User
from api.utils.auth import get_current_user


def create_external_payment(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    creditor: Creditor,
    payment: ExternalPaymentCreditorUpdate,
    new_invoice: Invoice,
):
    external_payment_invoice = Invoice(
        user_id=user.id,
        creditor_id=payment.creditor_id,
        purchase_date=new_invoice.purchase_date,
        title=new_invoice.title,
        value=payment.value,
        installments=new_invoice.installments,
        payment_type=new_invoice.payment_type,
        paid_status=new_invoice.paid_status,
        invoice_parent_id=new_invoice.id,
        creditor_parent_id=new_invoice.creditor_id,
    )
    db.add(external_payment_invoice)
    db.commit()
    db.refresh(external_payment_invoice)

    if creditor.creditor_type == "USER":
        query = select(Creditor).where(
            (Creditor.user_id == creditor.user_as_creditor_id)
            & (Creditor.user_as_creditor_id == user.id)
        )
        new_creditor = db.scalar(query)

        if new_creditor is None:
            new_creditor = Creditor(
                user_id=creditor.user_as_creditor_id,
                creditor_type="USER",
                name=user.username,
                user_as_creditor_id=user.id,
                due_date=new_invoice.responsible_creditor.due_date,
            )
            db.add(new_creditor)
            db.commit()
            db.refresh(new_creditor)

        elif not new_creditor.enabled:
            new_creditor = new_creditor.sqlmodel_update({"enabled": True})
            db.add(new_creditor)
            db.commit()
            db.refresh(new_creditor)

        user_creditor_invoice = Invoice(
            user_id=creditor.user_as_creditor_id,
            creditor_id=new_creditor.id,
            purchase_date=new_invoice.purchase_date,
            title=new_invoice.title,
            value=payment.value,
            installments=new_invoice.installments,
            payment_type=new_invoice.payment_type,
            paid_status=new_invoice.paid_status,
            creditor_parent_id=new_creditor.id,
        )
        db.add(user_creditor_invoice)
        db.commit()
        db.refresh(user_creditor_invoice)


def validate_invoice(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    invoice: InvoiceBase,
):
    if invoice.creditor_id is not None:
        query = select(Creditor).where(Creditor.id == invoice.creditor_id)
        creditor = db.scalar(query)
        if creditor is not None:
            if not creditor.enabled:
                raise HTTPException(
                    status_code=HTTPStatus.FORBIDDEN, detail="Unavailable creditor"
                )
            if creditor.user_id != user.id:
                raise HTTPException(
                    status_code=HTTPStatus.FORBIDDEN,
                    detail="You are not allowed to use this creditor",
                )
        else:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="The creditor provided does not exist",
            )

    if invoice.value is not None and invoice.value <= 0.0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="The purchase value cannot be zero or negative.",
        )

    if invoice.payment_type == "INSTALLMENT" and invoice.installments is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="If the purchase was made in installments, you must provide the installment amount.",
        )

    if (
        invoice.payment_type == "INSTALLMENT"
        and invoice.installments is not None
        and invoice.installments <= 0
    ):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="The number of installments cannot be zero or negative.",
        )

    creditors = []
    external_payments = invoice.external_payments

    if external_payments:
        creditors = []
        for item in external_payments:
            query = select(Creditor).where((Creditor.id == item.creditor_id))
            creditor = db.scalar(query)

            if creditor == None:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail="The entities reported do not exist",
                )
            if creditor in creditors:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail="Creditor duplicated",
                )
            creditors.append(creditor)

        total_value = 0

        for creditor, payment in zip(creditors, external_payments):
            total_value += payment.value

            if not creditor.enabled:
                raise HTTPException(
                    status_code=HTTPStatus.FORBIDDEN, detail="Unavailable creditor"
                )
            if creditor.user_id != user.id:
                raise HTTPException(
                    status_code=HTTPStatus.FORBIDDEN,
                    detail="You are not allowed to use this creditor",
                )
            if payment.value == 0:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail="The shared amount for the invoice cannot be zero.",
                )
            if invoice.value is not None and total_value > invoice.value:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail="Shared payment cannot be greater than the purchase amount",
                )

    return creditors, external_payments


def add_invoice_installments(installments, is_col: bool = False):
    if is_col or isinstance(installments, InstrumentedAttribute):
        return Invoice.purchase_date + (installments * text("INTERVAL '1 month'"))
    return Invoice.purchase_date + (literal(installments) * text("INTERVAL '1 month'"))


def add_month(date, value):
    day = func.extract("day", Creditor.due_date).cast(INTEGER)
    month = date.month
    year = date.year

    d = func.make_date(year, month, day)

    if isinstance(value, InstrumentedAttribute):
        return d + (value * text("INTERVAL '1 month'"))
    return d + (literal(value) * text("INTERVAL '1 month'"))


def subtract_month(date, value):
    day = func.extract("day", Creditor.due_date).cast(INTEGER)
    month = date.month - value
    year = date.year

    if month <= 0:
        month += 12
        year = date.year - 1

    day = case((month == 2, func.least(day, 28)), else_=day)
    return func.make_date(year, month, day)


def filter_by_unpaid_invoices(query, current_date):
    return query.where(
        case(
            (
                Invoice.payment_type != "FIXED",
                case(
                    (
                        Invoice.payment_type == "INSTALLMENT",
                        case(
                            (
                                current_date.day
                                > func.extract("day", Creditor.due_date),
                                (
                                    add_invoice_installments(1)
                                    <= add_month(current_date, 1)
                                )
                                & (
                                    add_invoice_installments(
                                        Invoice.installments + 1, True
                                    )
                                    > add_month(current_date, 0)
                                ),
                            ),
                            else_=(
                                (
                                    func.date(Invoice.purchase_date)
                                    <= add_month(current_date, 0)
                                )
                                & (
                                    add_invoice_installments(Invoice.installments)
                                    > add_month(current_date, 0)
                                )
                            ),
                        ),
                    ),
                    else_=(
                        case(
                            (
                                current_date.day
                                > func.extract("day", Creditor.due_date),
                                (
                                    (
                                        func.date(Invoice.purchase_date)
                                        <= add_month(current_date, 0)
                                    )
                                    & (
                                        add_invoice_installments(2)
                                        > add_month(current_date, 0)
                                    )
                                ),
                            ),
                            else_=(
                                (
                                    (
                                        func.date(Invoice.purchase_date)
                                        <= add_month(current_date, 0)
                                    )
                                    & (
                                        add_invoice_installments(1)
                                        > add_month(current_date, 0)
                                    )
                                )
                            ),
                        )
                    ),
                ),
            ),
            else_=(func.date(current_date) - func.date(Invoice.purchase_date) >= 0),
        ),
    )
