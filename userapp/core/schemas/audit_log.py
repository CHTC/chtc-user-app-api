from datetime import datetime
from typing import Optional

from pydantic import Field

from userapp.core.models.enum import AuditActionEnum
from userapp.core.schemas.general import BaseModel
from userapp.core.schemas.groups import GroupGet


class AuditLogGet(BaseModel):
    id: int
    occurred_at: datetime
    actor_id: Optional[int] = Field(default=None)
    action: AuditActionEnum
    group_id: Optional[int] = Field(default=None)
    member_user_id: Optional[int] = Field(default=None)
    member_group_id: Optional[int] = Field(default=None)
    caused_by: Optional[int] = Field(default=None)
    details: Optional[dict] = Field(default=None)
    # Null when the id is null, or when the user was deleted (the FK sets the id to null too)
    actor: Optional["UserGet"] = Field(default=None)
    member_user: Optional["UserGet"] = Field(default=None)
    member_group: Optional[GroupGet] = Field(default=None)


class AuditLogPost(BaseModel):
    """The shape services.audit.log writes. There is no Patch: the log is append-only."""

    action: AuditActionEnum
    actor_id: Optional[int] = Field(default=None)
    group_id: Optional[int] = Field(default=None)
    member_user_id: Optional[int] = Field(default=None)
    member_group_id: Optional[int] = Field(default=None)
    caused_by: Optional[int] = Field(default=None)
    details: Optional[dict] = Field(default=None)
