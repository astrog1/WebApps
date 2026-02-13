from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class QAItem(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=200)

    @field_validator("question", "answer", mode="before")
    @classmethod
    def coerce_to_str(cls, value: object) -> str:
        if isinstance(value, (int, float)):
            return str(value)
        if not isinstance(value, str):
            raise TypeError("Question and answer must be strings or numbers")
        return value.strip()

    @field_validator("question", "answer")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class DailySetPayload(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    level1: list[QAItem] = Field(min_length=40, max_length=200)
    level2: list[QAItem] = Field(min_length=8, max_length=200)
    level3: list[QAItem] = Field(min_length=8, max_length=200)

    @model_validator(mode="after")
    def ensure_unique_questions(self) -> "DailySetPayload":
        self._validate_unique_questions(self.level1, "level1")
        self._validate_unique_questions(self.level2, "level2")
        self._validate_unique_questions(self.level3, "level3")
        return self

    @staticmethod
    def _validate_unique_questions(items: list[QAItem], level_name: str) -> None:
        normalized = {item.question.strip().lower() for item in items}
        if len(normalized) != len(items):
            raise ValueError(f"{level_name} contains duplicate questions")
