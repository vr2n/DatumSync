from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, DateTime
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    email = Column(String(255), primary_key=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    picture = Column(String(512))
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
