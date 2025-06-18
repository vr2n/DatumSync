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

    
class ConvertedFile(Base):
    __tablename__ = "converted_files"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False)
    original_file = Column(String, nullable=False)
    converted_path = Column(String, nullable=False)
    format = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ValidationResult(Base):
    __tablename__ = "validation_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False)
    source_file = Column(String, nullable=False)
    target_file = Column(String, nullable=False)
    result_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default="success")
    created_at = Column(DateTime, default=datetime.utcnow)