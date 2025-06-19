from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Integer,DateTime
from datetime import datetime
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    email = Column(String(255), primary_key=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    picture = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    
class ConvertedFile(Base):
    __tablename__ = "converted_files"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False)
    original_file = Column(String, nullable=False)
    converted_path = Column(String, nullable=False)
    format = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ValidationResult(Base):
    __tablename__ = "validation_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False)
    source_file = Column(String, nullable=False)
    target_file = Column(String, nullable=False)
    result_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default="success")
    created_at = Column(DateTime, default=datetime.utcnow)
    
class NormalizedFile(Base):
    __tablename__ = "normalized_files"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False)
    input_file = Column(String, nullable=False)
    normalized_file = Column(String, nullable=False)
    status = Column(String, default="success")
    created_at = Column(DateTime, default=datetime.utcnow)
    
class ProfileResult(Base):
    __tablename__ = "profiling_results"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False)
    input_file = Column(String, nullable=False)
    profile_url = Column(String)
    drift_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)