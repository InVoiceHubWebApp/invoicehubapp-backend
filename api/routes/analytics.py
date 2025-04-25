from datetime import datetime, time, timedelta
from http import HTTPStatus
from typing import Annotated, List
from fastapi import APIRouter, Depends
from sqlalchemy import text, INTEGER
from sqlmodel import Session, and_, case, select, func
from sqlalchemy.orm import aliased

from api.config.database import get_db
from api.functions.invoices import filter_by_unpaid_invoices
from api.models.creditors import Creditor
from api.models.invoices import (
    Invoice,
    InvoiceStatsByCreditor,
    InvoiceStatsByMonth,
    InvoiceStatsByPaymentType,
    InvoiceStatsByWeek,
)
from api.models.users import User
from api.utils.auth import get_current_user

router = APIRouter()

ChildInvoice = aliased(Invoice)


@router.get(
    "/invoices_by_creditor",
    status_code=HTTPStatus.OK,
    response_model=List[InvoiceStatsByCreditor],
)
def get_invoices_by_creditor(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    current_date = datetime.now()

    subquery = (
        select(
            Creditor.id,
            Creditor.name,
            func.sum(
                case(
                    (ChildInvoice.id == None, 0),
                    else_=case(
                        (
                            ChildInvoice.payment_type == "INSTALLMENT",
                            ChildInvoice.value / ChildInvoice.installments,
                        ),
                        else_=ChildInvoice.value,
                    ),
                )
            ).label("amount_receivable"),
            func.sum(
                case(
                    (Invoice.invoice_parent_id == None, 0),
                    else_=case(
                        (
                            Invoice.payment_type == "INSTALLMENT",
                            Invoice.value / Invoice.installments,
                        ),
                        else_=Invoice.value,
                    ),
                )
            ).label("amount_payable"),
            case(
                (
                    Invoice.invoice_parent_id == None,
                    case(
                        (
                            Invoice.payment_type == "INSTALLMENT",
                            Invoice.value / Invoice.installments,
                        ),
                        else_=Invoice.value,
                    ),
                ),
                else_=0,
            ).label("total_value"),
        )
        .join(Invoice, Invoice.creditor_id == Creditor.id)
        .outerjoin(ChildInvoice, ChildInvoice.invoice_parent_id == Invoice.id)
        .group_by(Creditor.id, Creditor.name, Invoice.id)
    )

    subquery = subquery.where(
        and_(Invoice.user_id == user.id, Invoice.enabled, Invoice.paid_status != "PAID")
    )

    subquery = filter_by_unpaid_invoices(subquery, current_date).subquery()

    query = (
        select(
            Creditor.id,
            Creditor.name,
            func.sum(subquery.c.amount_receivable).label("amount_receivable"),
            func.sum(subquery.c.amount_payable).label("amount_payable"),
            func.sum(subquery.c.total_value).label("total_value"),
        )
        .join(subquery, subquery.c.id == Creditor.id)
        .group_by(Creditor.id, Creditor.name)
    )

    result = db.exec(query).mappings().all()
    return result


@router.get(
    "/invoices_by_month",
    status_code=HTTPStatus.OK,
    response_model=List[InvoiceStatsByMonth],
)
def get_invoices_by_month(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    current_date = datetime.now()

    invoices = (
        select(
            Invoice.id.label("invoice_id"),
            Invoice.value.label("value"),
            Invoice.installments.label("installments"),
            Invoice.payment_type.label("payment_type"),
            func.generate_series(
                case(
                    (
                        Invoice.purchase_date
                        >= func.make_date(
                            func.extract("year", Invoice.purchase_date).cast(INTEGER),
                            func.extract("month", Invoice.purchase_date).cast(INTEGER),
                            func.extract("day", Creditor.due_date).cast(INTEGER),
                        ),
                        Invoice.purchase_date + text("INTERVAL '1 month'"),
                    ),
                    else_=Invoice.purchase_date
                    + (
                        case(
                            (
                                Invoice.payment_type == "CASH",
                                text("INTERVAL '1 month'"),
                            ),
                            else_=text("INTERVAL '0 month'"),
                        )
                    ),
                ),
                case(
                    (
                        Invoice.purchase_date
                        >= func.make_date(
                            func.extract("year", Invoice.purchase_date).cast(INTEGER),
                            func.extract("month", Invoice.purchase_date).cast(INTEGER),
                            func.extract("day", Creditor.due_date).cast(INTEGER),
                        ),
                        Invoice.purchase_date + text("INTERVAL '1 month'"),
                    ),
                    else_=Invoice.purchase_date
                    + (
                        case(
                            (
                                Invoice.payment_type == "CASH",
                                text("INTERVAL '1 month'"),
                            ),
                            else_=text("INTERVAL '0 month'"),
                        )
                    ),
                )
                + case(
                    (
                        Invoice.payment_type == "INSTALLMENT",
                        (Invoice.installments - 1) * text("INTERVAL '1 month'"),
                    ),
                    else_=case(
                        (
                            Invoice.payment_type == "FIXED",
                            (12 - func.extract("month", Invoice.purchase_date))
                            * text("INTERVAL '2 month'"),
                        ),
                        else_=text("INTERVAL '0 month'"),
                    ),
                ),
                text("INTERVAL '1 month'"),
            ).label("date"),
        )
        .where(
            and_(
                Invoice.invoice_parent_id == None,
                Invoice.user_id == user.id,
                Invoice.enabled,
                Invoice.paid_status != "PAID",
            )
        )
        .join(Creditor, Creditor.id == Invoice.creditor_id)
    )

    query = (
        select(
            func.date_trunc("month", invoices.c.date).label("date"),
            func.sum(
                case(
                    (
                        invoices.c.payment_type == "INSTALLMENT",
                        invoices.c.value / invoices.c.installments,
                    ),
                    else_=invoices.c.value,
                )
            ).label("amount"),
        )
        .group_by(func.date_trunc("month", invoices.c.date))
        .order_by(func.date_trunc("month", invoices.c.date))
        .where(func.extract("year", invoices.c.date) == current_date.year)
    )

    result = db.exec(query).mappings().all()
    return result


@router.get(
    "/invoices_by_week",
    status_code=HTTPStatus.OK,
    response_model=List[InvoiceStatsByWeek],
)
def get_invoices_by_week(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    current_date = datetime.combine(datetime.today(), time.min)
    start_of_week = current_date - timedelta(days=current_date.weekday() + 1)
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)

    invoices = (
        select(
            (func.extract("dow", Invoice.purchase_date) + 1).label("day_of_week"),
            case(
                (
                    Invoice.payment_type == "INSTALLMENT",
                    Invoice.value / Invoice.installments,
                ),
                else_=Invoice.value,
            ).label("amount"),
        )
        .where(
            and_(
                Invoice.purchase_date >= start_of_week,
                Invoice.purchase_date <= end_of_week,
                Invoice.invoice_parent_id == None,
                Invoice.user_id == user.id,
                Invoice.enabled,
                Invoice.paid_status != "PAID",
            )
        )
        .group_by(Invoice.id)
    )

    query = (
        select(
            invoices.c.day_of_week,
            func.sum(invoices.c.amount).label("amount"),
        )
        .group_by(invoices.c.day_of_week)
        .order_by(invoices.c.day_of_week)
    )

    result = db.exec(query).mappings().all()
    return result


@router.get(
    "/invoices_by_payment_type",
    status_code=HTTPStatus.OK,
    response_model=List[InvoiceStatsByPaymentType],
)
def get_invoices_by_payment_type(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    current_date = datetime.now()

    subquery = select(
        Invoice.payment_type,
        case(
            (
                Invoice.payment_type == "INSTALLMENT",
                Invoice.value / Invoice.installments,
            ),
            else_=Invoice.value,
        ).label("amount"),
    ).group_by(Invoice.id)

    subquery = subquery.where(
        and_(
            Invoice.user_id == user.id,
            Invoice.enabled,
            Invoice.paid_status != "PAID",
            Invoice.invoice_parent_id == None,
        )
    )

    subquery = filter_by_unpaid_invoices(subquery, current_date).subquery()

    query = select(
        subquery.c.payment_type.label("payment_type"),
        func.sum(subquery.c.amount).label("amount"),
    ).group_by(subquery.c.payment_type)

    result = db.exec(query).mappings().all()
    return result
