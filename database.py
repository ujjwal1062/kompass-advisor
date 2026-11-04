import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

# 1. Try to get it locally (.env)
DATABASE_URL = os.getenv("DATABASE_URL")

# 2. If not found, try to get it from Streamlit Cloud Secrets
if not DATABASE_URL:
    try:
        import streamlit as st
        DATABASE_URL = st.secrets.get("DATABASE_URL")
    except Exception:
        pass

if not DATABASE_URL:
    raise ValueError("CRITICAL ERROR: DATABASE_URL is missing! Check your .env or Streamlit Secrets.")

# Create the database engine (Neon requires SSL)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our models
Base = declarative_base()

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()