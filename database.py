import os
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# 1. Try to load from local .env file
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# 2. If not found, try to load from Streamlit Cloud Secrets
if not DATABASE_URL:
    try:
        DATABASE_URL = st.secrets["DATABASE_URL"]
    except Exception:
        pass

# 3. If still not found, throw a clear error
if not DATABASE_URL:
    raise ValueError("CRITICAL ERROR: DATABASE_URL is missing!")

# --- THE FIX: Force SQLAlchemy to use the psycopg2 driver ---
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# Create the database engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()