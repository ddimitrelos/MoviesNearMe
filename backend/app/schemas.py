from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class MovieOut(BaseModel):
    id: int
    slug: str
    title: str
    original_title: Optional[str] = None
    genre: Optional[str] = None
    duration_min: Optional[int] = None
    poster_url: Optional[str] = None

    class Config:
        from_attributes = True


class CinemaOut(BaseModel):
    id: int
    slug: str
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    region: Optional[str] = None
    is_summer: bool = False

    class Config:
        from_attributes = True


class ScreeningOut(BaseModel):
    id: int
    start_time: datetime
    hall: Optional[str] = None
    movie: MovieOut
    cinema: CinemaOut

    class Config:
        from_attributes = True


# A cinema plus the screenings relevant to the current query (used by the map).
class CinemaWithScreenings(CinemaOut):
    screenings: List["ScreeningBrief"] = []


class ScreeningBrief(BaseModel):
    id: int
    start_time: datetime
    hall: Optional[str] = None
    movie: MovieOut

    class Config:
        from_attributes = True


CinemaWithScreenings.model_rebuild()
