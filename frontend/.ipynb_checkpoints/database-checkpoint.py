import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise ValueError("❌ DATABASE_URL not found in environment")

# ✅ Recommended SSL options for CockroachDB Cloud
engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "verify-full"},  # Use "require" if not using custom CA
    future=True,
    echo=False  # Change to True for SQL debug logs
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
