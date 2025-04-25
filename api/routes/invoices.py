from datetime import datetime, time
from dateutil.relativedelta import relativedelta
from http import HTTPStatus
import math
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func
from sqlalchemy import not_, and_, or_, case, text, INTEGER

from api.config.database import get_db
from api.functions.invoices import create_external_payment, validate_invoice
from api.models.creditors import Creditor
from api.models.invoices import (
    Invoice,
    InvoiceBase,
    InvoiceBasic,
    InvoicePaidBase,
    InvoicePublic,
    InvoiceUpdateBase,
)
from api.models.pagination import Page
from api.models.users import User
from api.utils.auth import get_api_key, get_current_user

router = APIRouter()


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    response_model=InvoiceBase,
)
def create_invoice(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    invoice: InvoiceBase,
):
    creditors, external_payments = validate_invoice(user, db, invoice)

    new_invoice = Invoice(
        user_id=user.id,
        creditor_id=invoice.creditor_id,
        purchase_date=datetime.combine(invoice.purchase_date, time.min),
        title=invoice.title,
        value=invoice.value,
        installments=invoice.installments,
        payment_type=invoice.payment_type,
        paid_status=invoice.paid_status,
        creditor_parent_id=invoice.creditor_id,
    )

    db.add(new_invoice)
    db.commit()
    db.refresh(new_invoice)

    if creditors:
        for creditor, payment in zip(creditors, external_payments):
            create_external_payment(user, db, creditor, payment, new_invoice)

    new_invoice.sqlmodel_update({"external_payments": external_payments})
    return new_invoice


@router.get(
    "",
    status_code=HTTPStatus.OK,
    response_model=Page[InvoicePublic],
)
def read_invoices(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(gt=0)] = 25,
):
    offset = page * size
    query = select(Invoice).where(
        (Invoice.user_id == user.id)
        & (Invoice.invoice_parent_id == None)
        & (Invoice.enabled)
    )

    total = db.scalar(query.with_only_columns(func.count(Invoice.id)))
    pages = math.ceil(total / size)

    query = query.group_by(Invoice.id).order_by(Invoice.purchase_date.desc())
    invoices = db.scalars(query.offset(offset).limit(size))

    payments = []
    now = datetime.now()
    current_date = datetime(now.year, now.month, 1)

    for invoice in invoices:
        payment = invoice.model_dump()
        creditor = invoice.responsible_creditor
        purchase_date = invoice.purchase_date + relativedelta(months=+1)
        if invoice.purchase_date.day > creditor.due_date.day:
            purchase_date += relativedelta(months=+1)
        if payment["installments"] is not None:
            payment["installment_value"] = invoice.value / invoice.installments
            payment["last_payment_date"] = purchase_date + relativedelta(
                months=+invoice.installments - 1
            )
        else:
            payment["last_payment_date"] = purchase_date
        payment["responsible_creditor"] = invoice.responsible_creditor
        payment["external_payments"] = invoice.external_payments
        purchase_date = datetime(
            invoice.purchase_date.year, invoice.purchase_date.month, 1
        )
        payment["installment_paid"] = (
            relativedelta(dt1=current_date, dt2=purchase_date).months - 1
        )
        if payment["installment_paid"] < 0:
            payment["installment_paid"] = 0
        payments.append(payment)

    return {
        "items": payments,
        "page": page,
        "size": size,
        "pages": pages,
        "total": total,
    }


@router.patch(
    "/mark_all_as_paid",
    status_code=HTTPStatus.OK,
    response_model=List[InvoiceBasic],
)
def mark_all_as_paid(
    _: Annotated[str, Depends(get_api_key)],
    db: Annotated[Session, Depends(get_db)],
):
    now = datetime.now()

    date = case(
        (
            func.extract("day", Invoice.purchase_date)
            > func.extract("day", Creditor.due_date),
            func.make_date(
                func.extract("year", Invoice.purchase_date).cast(INTEGER),
                func.extract("month", Invoice.purchase_date).cast(INTEGER),
                func.extract("day", Creditor.due_date).cast(INTEGER),
            )
            + text("INTERVAL '1 month'"),
        ),
        else_=func.make_date(
            func.extract("year", Invoice.purchase_date).cast(INTEGER),
            func.extract("month", Invoice.purchase_date).cast(INTEGER),
            func.extract("day", Creditor.due_date).cast(INTEGER),
        ),
    )

    subquery = (
        select(
            Invoice.id,
            Invoice.title,
            Invoice.purchase_date,
            case(
                (
                    Invoice.payment_type == "INSTALLMENT",
                    date + (Invoice.installments * text("INTERVAL '1 month'")),
                ),
                else_=date + text("INTERVAL '1 month'"),
            ).label("date"),
        )
        .join(Creditor, Creditor.id == Invoice.creditor_id)
        .where(
            and_(
                Invoice.invoice_parent_id == None,
                Invoice.enabled,
                Invoice.paid_status != "PAID",
                or_(
                    Invoice.payment_type == "INSTALLMENT",
                    Invoice.payment_type == "CASH",
                ),
            )
        )
    ).subquery()

    query = select(
        subquery.c.id.label("id"),
        subquery.c.purchase_date.label("purchase_date"),
        subquery.c.title.label("title"),
        subquery.c.date.label("date"),
    ).where(func.make_date(now.year, now.month, now.day) > subquery.c.date)

    results = db.exec(query).mappings().all()

    for purchase in results:
        query = select(Invoice).where(Invoice.id == purchase.id)
        invoice = db.scalar(query)

        for payment in invoice.external_payments:
            payment.sqlmodel_update(
                {"updated_at": datetime.now(), "paid_status": "OVERDUE"}
            )
            db.add(payment)
            db.commit()
            db.refresh(payment)

        invoice.sqlmodel_update(
            {"updated_at": datetime.now(), "paid_status": "OVERDUE"}
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
    return results


@router.patch("/mark_as_paid", status_code=HTTPStatus.NO_CONTENT)
def mark_as_paid(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    body: InvoicePaidBase,
):
    ids = body.ids
    for id in ids:
        query = select(Invoice).where((Invoice.id == id) & (Invoice.enabled))
        invoice = db.scalar(query)

        if invoice is not None:
            if invoice.author.id != user.id:
                raise HTTPException(
                    status_code=HTTPStatus.FORBIDDEN,
                    detail="You do not have permission to update this item.",
                )
        else:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="Item not found"
            )

        for payment in invoice.external_payments:
            payment.sqlmodel_update(
                {"updated_at": datetime.now(), "paid_status": "PAID"}
            )
            db.add(payment)
            db.commit()
            db.refresh(payment)

        invoice.sqlmodel_update({"updated_at": datetime.now(), "paid_status": "PAID"})
        db.add(invoice)
        db.commit()
        db.refresh(invoice)


@router.patch(
    "/{id}",
    status_code=HTTPStatus.OK,
    response_model=InvoiceBase,
)
def update_invoice(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    id: int,
    invoice: InvoiceUpdateBase,
):
    query = select(Invoice).where((Invoice.id == id) & (Invoice.enabled))
    db_invoice = db.scalar(query)

    if db_invoice is not None:
        if db_invoice.author.id != user.id:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="You do not have permission to update this item.",
            )
        if not db_invoice.enabled:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT, detail="Item is disabled."
            )
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found")

    creditors, external_payments = validate_invoice(user, db, invoice)

    if invoice.purchase_date != None:
        db_invoice.sqlmodel_update(
            {"purchase_date": datetime.combine(invoice.purchase_date, time.min)}
        )

    if invoice.external_payments != None:
        payments_ids = [payment.id for payment in external_payments]
        total_value = 0

        for payment in db_invoice.external_payments:
            query = select(Invoice).where(
                (Invoice.id == payment.id) & (Invoice.enabled)
            )
            external_payment_invoice = db.scalar(query)

            if external_payment_invoice.id not in payments_ids:
                total_value -= external_payment_invoice.value
                db.delete(external_payment_invoice)
                db.commit()

        db.refresh(db_invoice)
        if creditors:
            for creditor, payment in zip(creditors, external_payments):
                if payment.id != None:  # Edit existing purchase
                    query = select(Invoice).where(
                        (Invoice.id == payment.id) & (Invoice.enabled)
                    )
                    external_payment_invoice = db.scalar(query)

                    if external_payment_invoice != None:
                        total_value += payment.value
                        if total_value > db_invoice.value:
                            raise HTTPException(
                                status_code=HTTPStatus.BAD_REQUEST,
                                detail="Shared payment cannot be greater than the purchase amount",
                            )

                        data = payment.model_dump(exclude_unset=True)
                        external_payment_invoice.sqlmodel_update(data)
                        external_payment_invoice.sqlmodel_update(
                            {"updated_at": datetime.now()}
                        )
                        db.add(external_payment_invoice)
                        db.commit()
                else:  # if it doesn't exist, then create one
                    total_value += payment.value

                    if total_value > db_invoice.value:
                        raise HTTPException(
                            status_code=HTTPStatus.BAD_REQUEST,
                            detail="Shared payment cannot be greater than the purchase amount",
                        )
                    create_external_payment(user, db, creditor, payment, db_invoice)

        db.refresh(db_invoice)

    data = invoice.model_dump(exclude_unset=True)
    db_invoice.sqlmodel_update(data)
    db_invoice.sqlmodel_update({"updated_at": datetime.now()})
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)

    return db_invoice


@router.delete("/{id}", status_code=HTTPStatus.NO_CONTENT)
def delete_invoice(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    id: int,
):
    query = select(Invoice).where((Invoice.id == id) & (Invoice.enabled))
    invoice = db.scalar(query)

    if invoice is not None:
        if invoice.author.id != user.id:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="You do not have permission to delete this item.",
            )
        if not invoice.enabled:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT, detail="Item is already disabled."
            )
    else:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found")

    for payment in invoice.external_payments:
        payment.sqlmodel_update({"enabled": False, "updated_at": datetime.now()})
        db.add(payment)
        db.commit()
        db.refresh(payment)

    invoice.sqlmodel_update({"enabled": False, "updated_at": datetime.now()})
    db.add(invoice)
    db.commit()
    db.refresh(invoice)


# async def update_training_model_by_id(

# ):
#   return await model_training.update_training_model_by_id(
#     db, training_model_id, training_model
#   )
