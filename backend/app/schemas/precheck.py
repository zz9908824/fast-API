import uuid
from datetime import datetime
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


class MatterVersionPublish(SQLModel):
    """Administrator confirmation for publishing one reviewed matter version."""

    expected_config_revision: int = Field(gt=0)


class ReviewSectionUpdate(SQLModel):
    expected_config_revision: int = Field(gt=0)
    note: str = Field(default="", max_length=2000)


class MatterStatusConfigUpdate(SQLModel):
    expected_config_revision: int = Field(gt=0)
    acceptance_condition_raw: str = Field(default="", max_length=2000)
    channels: list[str] = Field(default_factory=list, max_length=20)
    uncertainties: list[str] = Field(default_factory=list, max_length=30)


class PolicySourceConfigUpdate(SQLModel):
    expected_config_revision: int = Field(gt=0)
    publisher: str = Field(default="", max_length=200)
    url: str = Field(min_length=1, max_length=2000)


class ServiceLocationConfigUpdate(SQLModel):
    expected_config_revision: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=100)
    opening_hours: str | None = None
    official_entry_url: str | None = None
    verification_status: Literal["pending", "verified", "unavailable"] = "pending"
    checked_at: datetime | None = None
    source_id: uuid.UUID | None = None


class MaterialRequirementCreate(SQLModel):
    expected_config_revision: int = Field(gt=0)
    material_type_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    requirement_level: Literal["required", "optional"] = "required"
    format_requirements: str | None = None


class MaterialRequirementUpdate(SQLModel):
    expected_config_revision: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    requirement_level: Literal["required", "optional"] = "required"
    format_requirements: str | None = None


class MaterialAcquisitionMethodCreate(SQLModel):
    expected_config_revision: int = Field(gt=0)
    requirement_id: uuid.UUID
    method_type: Literal["online_download", "online_apply", "in_person", "self_prepare", "department_fetch", "on_site"]
    title: str = Field(min_length=1, max_length=200)
    steps: str | None = None
    entry_url: str | None = Field(default=None, max_length=2000)


class MaterialAcquisitionMethodUpdate(SQLModel):
    expected_config_revision: int = Field(gt=0)
    requirement_id: uuid.UUID
    method_type: Literal["online_download", "online_apply", "in_person", "self_prepare", "department_fetch", "on_site"]
    title: str = Field(min_length=1, max_length=200)
    steps: str | None = None
    entry_url: str | None = Field(default=None, max_length=2000)
