from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, DateTime
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    email = Column(String, primary_key=True, index=True)
    name = Column(String)
    picture = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
