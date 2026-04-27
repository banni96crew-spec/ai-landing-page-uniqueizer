from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_url: str = Field(min_length=1)


class JobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    status: str
    created_at: datetime
    target_url: str


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    job_id: int
    file_path: str
    file_size: int | None = None
    hash: str | None = None
    created_at: datetime


class JobDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    status: str
    target_url: str
    created_at: datetime
    updated_at: datetime
    artifact: ArtifactResponse | None = None
    progress_pct: int


class JobLogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: str
    message: str
    timestamp: datetime


class SettingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    value: str


class SettingUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    value: str
