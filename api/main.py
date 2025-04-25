from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import creditors, users, token, invoices, analytics, root


def main():
    app = FastAPI(title="Invoice Hub", version="1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    app.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
    app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
    app.include_router(creditors.router, prefix="/creditors", tags=["Creditors"])
    app.include_router(users.router, prefix="/users", tags=["Users"])
    app.include_router(token.router, prefix="/token", tags=["Authentication"])
    app.include_router(root.router, tags=["Root"])

    return app
