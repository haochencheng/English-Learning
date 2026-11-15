from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, Field, HttpUrl, ConfigDict, field_validator

Deck = Literal["job", "ielts", "business"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WordInput(Model):
    deck: Deck
    term: str = Field(min_length=1, max_length=150)
    pos: str = Field(min_length=1, max_length=40)
    meaning: str = Field(min_length=1, max_length=400)
    collocation: str = Field(default="", max_length=400)
    example: str = Field(min_length=1, max_length=2000)
    translation: str = Field(min_length=1, max_length=2000)
    source_url: HttpUrl
    example_kind: Literal["example", "definition"] = "example"
    source_label: str = Field(default="", max_length=300)


class ReviewInput(Model):
    word_id: str
    rating: Literal["again", "hard", "good"]
    request_id: str = Field(min_length=8, max_length=100)
    timezone: str = "Asia/Shanghai"

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("未知时区")
        return value


class DraftInput(Model):
    text: str = Field(max_length=20000)


class ReviewState(Model):
    stage: int = Field(ge=0, le=5, strict=True)
    due: int = Field(ge=0, le=253402300799000, strict=True)
    count: int = Field(ge=1, strict=True)


class LegacyProgress(Model):
    version: Literal[1]
    reviews: dict[str, ReviewState]
    days: dict[str, list[str]]
    drafts: dict[str, str]

    @field_validator("days")
    @classmethod
    def valid_days(cls, value):
        for day in value:
            date.fromisoformat(day)
        return value

    @field_validator("drafts")
    @classmethod
    def valid_drafts(cls, value):
        if any(len(text) > 20000 for text in value.values()):
            raise ValueError("草稿超过 20,000 字符")
        return value


class QuizInput(Model):
    word_id: str
    answer: str = Field(min_length=1, max_length=500)
    request_id: str = Field(min_length=8, max_length=100)


class VideoImport(Model):
    url: str = Field(min_length=5, max_length=500)
    deck: Deck = "job"


class VideoProgress(Model):
    notes: str | None = Field(default=None, max_length=20000)
    favorite: bool | None = None
    completed: bool | None = None


class SyncInput(Model):
    mode: Literal["curated", "search", "channels"] = "curated"
    deck: Deck = "job"
    query: str = Field(default="", max_length=150)
    limit: int = Field(default=30, ge=1, le=100)
