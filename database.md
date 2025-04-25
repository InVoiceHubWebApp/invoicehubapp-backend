```mermaid
erDiagram
    User ||--o{ Creditor : has
    User ||--o{ Invoice : has
    User ||--o{ IncomeSources : has
    Creditor ||--o{ Invoice : has
    Invoice ||--o{ Invoice : has

    User {
        id Integer PK 
        name Text
        lastname Text
        email Text
        username Text
        password Text
        spending_limit Float
        reserve_fund Float
    }

    IncomeSources {
        id Integer PK
        user_id Integer FK
        value Float
    }

    Creditor {
        id Integer PK
        user_id Integer FK
        user_as_creditor_id Integer FK
        creditor_type CreditorTypeEnum
        name Text
        due_date Date
        limit_value Float
        enabled Bool
    }

    Invoice {
        id Integer PK
        user_id Integer FK
        creditor_id Integer FK
        purchase_date Date
        title Text
        value Float
        installments Integer
        payment_type PaymentTypeEnum
        paid Bool
        invoice_parent_id Integer FK
        enabled Bool
    }

    CreditorTypeEnum{
        USER Text
        BANK Text
        PAYMENT_SLIP Text
        PUBLIC_PERSON Text
    }

    PaymentTypeEnum{
        INSTALLMENT Text
        CASH Text
        FIXED Text
    }
```

| Value (left) | Value (right) | Meaning                         |
|--------------|---------------|---------------------------------|
|\|o           |o\|            | Zero or one                     |
|\|\|          |\|\|           | Exactly one                     |
|}o            |o{             | Zero or more (no upper limit)   |
|}\|           |\|{            | One or more (no upper limit)    |