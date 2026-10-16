import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field
from sqlmodel import SQLModel


class ApplicationCreate(SQLModel):
    matter_id: uuid.UUID
    matter_version_id: uuid.UUID
    # A user must explicitly choose this after being told that an unfinished
    # preparation record for the same matter already exists.
    create_new: bool = False


class ApplicationDisplayNameUpdate(SQLModel):
    display_name: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(gt=0)


class ScenarioUpdate(SQLModel):
    answers: dict = Field(default_factory=dict)
    mode: Literal["draft", "submit"] = "draft"
    expected_revision: int = Field(gt=0)


class QuestionnaireSubmit(SQLModel):
    """Minimal, resumable resident questionnaire for a material-preparation record."""

    prepared_for: Literal["self", "other"]
    applicant_name: str = Field(min_length=1, max_length=100)
    submission_plan: Literal["applicant", "agent", "unknown"]
    agent_relationship: str | None = Field(default=None, max_length=80)
    agent_name: str | None = Field(default=None, max_length=100)
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


class ExtraMaterialPreparationUpdate(SQLModel):
    declaration: Literal["not_ready", "ready", "unknown"]
    expected_revision: int = Field(gt=0)


class MaterialReviewStart(SQLModel):
    """Request a full or one-material preparation-only model review."""

    provider: Literal["local", "cloud"]
    material_id: uuid.UUID | None = None
    item_kind: Literal["requirement", "extra"] | None = None
    expected_revision: int = Field(gt=0)


class CaseReviewItemDecision(SQLModel):
    """One administrator decision for a model-flagged material item."""

    material_name: str = Field(min_length=1, max_length=200)
    decision: Literal["pass", "reupload"]
    note: str = Field(default="", max_length=1000)


class CaseReviewComplete(SQLModel):
    """Finish a claimed review task with decisions for every flagged item."""

    item_decisions: list[CaseReviewItemDecision] = Field(min_length=1, max_length=100)
    comment: str = Field(default="", max_length=2000)


class DelegationMaterialConfig(SQLModel):
    material_code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    requirement_level: Literal["required", "optional"] = "required"
    submission_mode: Literal["user_upload", "department_fetch", "on_site", "no_submission"] = "on_site"
    applicability_expr: dict = Field(default_factory=lambda: {"op": "always"})


class DelegationPolicyUpdate(SQLModel):
    expected_config_revision: int = Field(gt=0)
    delegation_allowed: bool = False
    applicant_must_attend: bool = False
    relationship_required: bool = False
    allowed_relationships: list[str] = Field(default_factory=list, max_length=20)
    condition_expr: dict = Field(default_factory=lambda: {"op": "always"})
    questionnaire_required: bool = False
    source_id: uuid.UUID | None = None
    materials: list[DelegationMaterialConfig] = Field(default_factory=list, max_length=30)


class MatterVersionPublish(SQLModel):
    """Administrator confirmation for publishing one reviewed matter version."""

    expected_config_revision: int = Field(gt=0)


class MatterVersionDraftCopy(SQLModel):
    """Expected revision of a finished version that will be copied into a draft."""

    expected_config_revision: int = Field(gt=0)


class MatterNameUpdate(SQLModel):
    """Rename a draft without changing a released version's public name."""

    expected_config_revision: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)


class MatterDisable(SQLModel):
    expected_config_revision: int = Field(gt=0)


class GovernmentDetailsUpdate(SQLModel):
    expected_config_revision: int = Field(gt=0)
    government_profile: dict[str, str] = Field(default_factory=dict)
    processing_steps: list[dict] = Field(default_factory=list)
    legal_bases: list[str] = Field(default_factory=list)
    field_evidence: list[dict] = Field(default_factory=list)


class GovernmentDetailsConfirm(SQLModel):
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
