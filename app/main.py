from fastapi import FastAPI
from sqlmodel import SQLModel
from app.db import engine
from app.api import products  # your products router

app = FastAPI()

@app.on_event("startup")
def on_startup():
    # Create database tables
    SQLModel.metadata.create_all(engine)

@app.get("/")
def root():
    return {"message": "Welcome to Bharat Product Intelligence API"}

# Include your products router under /api prefix
app.include_router(products.router, prefix="/api")
