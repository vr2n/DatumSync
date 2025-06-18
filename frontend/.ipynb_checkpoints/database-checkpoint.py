import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL not found in environment")

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "sslmode": "verify-full",
        "sslrootcert": "/opt/render/project/src/frontend/certs/root.crt",
        "options": "-c server_version=13"
    },
    future=True,
    echo=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
