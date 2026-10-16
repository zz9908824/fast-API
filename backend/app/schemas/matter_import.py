from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class MatterImportStart(BaseModel):
    """Administrator-supplied context; it is not treated as source evidence."""

    model_config = ConfigDict(extra="forbid")

    region_code: str = Field(min_length=1, max_length=32)
    region_name: str = Field(min_length=1, max_length=100)
    source_url: HttpUrl
    source_kind: Literal["guide", "policy", "template", "faq", "contact"] = "guide"
    model_provider: Literal["local", "cloud"] = "local"
    pasted_text: str = Field(min_length=20, max_length=100_000)
    source_title_override: str | None = Field(default=None, max_length=300)
    import_note: str | None = Field(default=None, max_length=2000)


class ImportMatter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    official_code: str | None = Field(default=None, max_length=150)
    description: str | None = None


class ImportScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acceptance_condition_raw: str | None = None
    channels: list[str] = Field(default_factory=list)


class ImportSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    publisher: str | None = Field(default=None, max_length=200)
    published_date: str | None = None


class ImportLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=100)
    opening_hours: str | None = None
    official_entry_url: str | None = None


class ImportAcquisitionMethod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_key: str = Field(min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=200)
    method_type: Literal["online_download", "online_apply", "in_person", "self_prepare", "department_fetch", "on_site"] | None = None
    steps: str | None = None
    entry_url: str | None = None


class ImportMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_key: str = Field(min_length=1, max_length=80)
    name: str | None = Field(default=None, max_length=200)
    type_name_candidate: str | None = Field(default=None, max_length=150)
    requirement_level: Literal["required", "optional"] | None = None
    provider_role: Literal["applicant", "agent", "spouse", "household_member"] | None = None
    submission_mode: Literal["user_upload", "department_fetch", "on_site", "no_submission"] | None = None
    original_required: bool | None = None
    copy_count: int | None = Field(default=None, ge=0)
    min_pages: int | None = Field(default=None, gt=0)
    format_requirements: str | None = None
    acquisition_methods: list[ImportAcquisitionMethod] = Field(default_factory=list)


class ImportDelegationMaterial(BaseModel):
    """A material needed only when an approved agent handles the matter."""

    model_config = ConfigDict(extra="forbid")

    local_key: str = Field(min_length=1, max_length=80)
    name: str | None = Field(default=None, max_length=200)
    requirement_level: Literal["required", "optional"] | None = None
    submission_mode: Literal["user_upload", "department_fetch", "on_site", "no_submission"] | None = None


class ImportDelegationCandidate(BaseModel):
    """Unverified delegation facts extracted from the submitted source."""

    model_config = ConfigDict(extra="forbid")

    delegation_allowed: bool | None = None
    materials: list[ImportDelegationMaterial] = Field(default_factory=list)


class ImportUncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str = Field(min_length=1, max_length=300)
    kind: Literal["missing", "conflict", "unreadable", "manual_needed"]
    message: str = Field(min_length=1, max_length=1000)
    blocking: bool = False


class ImportProcessStep(BaseModel):
    """One official handling step retained verbatim for administrator review."""

    model_config = ConfigDict(extra="forbid")

    step: str | None = None
    time_limit: str | None = None
    result: str | None = None
    review_standard: str | None = None


class ImportFieldEvidence(BaseModel):
    """A field's source quote; page is null when the model cannot identify it."""

    model_config = ConfigDict(extra="forbid")

    field_path: str = Field(min_length=1, max_length=300)
    page_number: int | None = Field(default=None, ge=1)
    quote: str = Field(min_length=1, max_length=3000)


class MatterImportCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matter: ImportMatter
    scope: ImportScope
    source: ImportSource
    location: ImportLocation
    materials: list[ImportMaterial] = Field(default_factory=list)
    delegation: ImportDelegationCandidate = Field(default_factory=ImportDelegationCandidate)
    uncertainties: list[ImportUncertainty] = Field(default_factory=list)
    # These fields preserve the government-portal data that does not fit the
    # resident-facing core tables. Chinese official labels are retained as keys.
    government_profile: dict[str, str] = Field(default_factory=dict)
    processing_steps: list[ImportProcessStep] = Field(default_factory=list)
    legal_bases: list[str] = Field(default_factory=list)
    field_evidence: list[ImportFieldEvidence] = Field(default_factory=list)


class ImportCoreCandidate(BaseModel):
    """Fields extracted independently from materials, location and channels."""

    model_config = ConfigDict(extra="forbid")

    matter: ImportMatter = Field(default_factory=ImportMatter)
    scope: ImportScope = Field(default_factory=ImportScope)
    source: ImportSource = Field(default_factory=ImportSource)
    uncertainties: list[ImportUncertainty] = Field(default_factory=list)


class ImportMaterialsCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materials: list[ImportMaterial] = Field(default_factory=list)


class ImportLocationCandidate(BaseModel):
    """A location deliberately excludes phone so it can be extracted separately."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    address: str | None = None
    opening_hours: str | None = None
    official_entry_url: str | None = None


class ImportPhoneCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str | None = Field(default=None, max_length=100)


class ImportChannelsCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channels: list[str] = Field(default_factory=list)
