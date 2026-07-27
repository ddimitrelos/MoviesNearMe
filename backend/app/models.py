from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    ForeignKey,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class Cinema(Base):
    __tablename__ = "cinemas"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    address = Column(String)
    phone = Column(String)
    lat = Column(Float)
    lng = Column(Float)
    region = Column(String)
    is_summer = Column(Boolean, default=False, nullable=False)
    source_url = Column(String)

    screenings = relationship(
        "Screening", back_populates="cinema", cascade="all, delete-orphan"
    )


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    original_title = Column(String)
    genre = Column(String)
    duration_min = Column(Integer)
    poster_url = Column(String)
    source_url = Column(String)

    screenings = relationship(
        "Screening", back_populates="movie", cascade="all, delete-orphan"
    )


class Screening(Base):
    __tablename__ = "screenings"
    __table_args__ = (
        UniqueConstraint(
            "cinema_id", "movie_id", "start_time", "hall", name="uq_screening"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    cinema_id = Column(Integer, ForeignKey("cinemas.id"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    start_time = Column(DateTime, nullable=False, index=True)
    hall = Column(String)
    scraped_at = Column(DateTime, default=datetime.utcnow)

    cinema = relationship("Cinema", back_populates="screenings")
    movie = relationship("Movie", back_populates="screenings")
