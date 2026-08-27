from fastapi import FastAPI
from services.auth.src.router import router

app = FastAPI(title="Auth Service")

app.include_router(router)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "auth",
    }