from fastapi import APIRouter

router = APIRouter()


@router.get("/", tags=["Root"])
async def get_root():
    response = {
        "name": "Invoice Hub",
        "status": "It works! 🔪💀",
    }
    return response
