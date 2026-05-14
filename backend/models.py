from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from database import Base  # same folder import

class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    category = Column(String, nullable=False)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String, index=True, nullable=False)
    body = Column(String, nullable=False)
    category = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    ml_label = Column(String, nullable=True, index=True)  # ML / manual label
    created_at = Column(DateTime, default=datetime.utcnow)

