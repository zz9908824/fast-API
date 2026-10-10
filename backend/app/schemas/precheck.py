import uuid
from typing import Literal

from pydantic import Field
from sqlmodel import SQLModel


class ApplicationCreate(SQLModel):
    matter_id: uuid.UUID
    matter_version_id: uuid.UUID


class ScenarioUpdate(SQLModel):
    answers: dict = Field(default_factory=dict)
    mode: Literal["draft", "submit"] = "draft"
    expected_revision: int = Field(gt=0)


class ParticipantCreate(SQLModel):
    role_code: Literal["applicant", "agent", "spouse", "household_member"]
    display_name: str | None = Field(default=None, max_length=100)
    identity_payload: dict = Field(default_factory=dict)
    expected_revision: int = Field(gt=0)


class PreparationItemUpdate(SQLModel):
    requirement_id: uuid.UUID
    participant_id: uuid.UUID | None = None
    declaration: Literal["not_ready", "ready", "unknown"]
    expected_revision: int = Field(gt=0)
