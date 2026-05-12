from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sessdata = Column(Text)
    bili_jct = Column(Text)
    buvid3 = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String(100), unique=True, nullable=False)
    channel_name = Column(String(200), nullable=False)
    channel_url = Column(String(500), nullable=False)
    custom_name = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(50), unique=True, nullable=False)
    channel_id = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    url = Column(String(500), nullable=False)
    thumbnail = Column(String(500))
    published_at = Column(DateTime)
    duration = Column(Integer)
    subtitles = Column(Text)
    has_new = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    checked_at = Column(DateTime, default=datetime.utcnow)