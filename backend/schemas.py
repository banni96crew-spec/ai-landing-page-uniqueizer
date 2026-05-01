from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


PlanLiteral = Literal["trial", "standard", "premium"]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    telegram_username: str = Field(default="", max_length=64)

    @field_validator("login")
    @classmethod
    def normalize_login(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("login cannot be empty")
        return normalized

    @field_validator("telegram_username")
    @classmethod
    def normalize_telegram_username(cls, value: str) -> str:
        return value.strip().lstrip("@")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("login")
    @classmethod
    def normalize_login(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("login cannot be empty")
        return normalized


class AccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str
    telegram_username: str
    plan: PlanLiteral
    sites_used: int = Field(ge=0)
    sites_remaining: int | None = Field(default=None, ge=0)


class LogoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    detail: str


class LicenseVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activation_key: str = Field(min_length=1, max_length=256)

    @field_validator("activation_key")
    @classmethod
    def normalize_activation_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("activation_key cannot be empty")
        return normalized
