from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, DateTime
import datetime
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    email = Column(String(255), primary_key=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    picture = Column(String(512))
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class ConversionLog(Base):
    __tablename__ = "conversion_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    format = Column(String, nullable=False)
    gcs_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)