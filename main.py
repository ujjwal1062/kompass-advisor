from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
import models
from database import engine, get_db
from sqlalchemy import text

# Create tables in Neon
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Germany Study Advisor API")

@app.get("/")
def read_root():
    return {"message": "Welcome to the Germany Study Advisor API"}

@app.get("/test-db")
def test_db(db: Session = Depends(get_db)):
    try:
        # Simple query to check if connection works
        result = db.execute(text("SELECT version();")).fetchone()
        return {"status": "Connected!", "db_version": result[0]}
    except Exception as e:
        return {"status": "Error", "details": str(e)}