from datetime import datetime
from typing import Optional

from pydantic import Field, model_validator, EmailStr

from userapp.core.models.enum import FormStatusEnum, FormTypeEnum, PositionEnum, RoleEnum
from userapp.core.schemas.general import BaseModel
from userapp.core.schemas.users import UserGet, UserSubmitPost


class UserFormPatch(BaseModel):
    status: FormStatusEnum

    preserve_existing_data: Optional[bool] = Field(default=False)
    email: Optional[EmailStr] = Field(default=None)
    project_id: Optional[int] = Field(default=None)
    user_position: Optional[PositionEnum] = Field(default=None)
    submit_nodes: Optional[list["UserSubmitPost"]] = Field(default=None)


class UserFormTableSchema(BaseModel):
    """Schema for the database representation of a UserForm."""
    id: int
    email: Optional[EmailStr] = Field(default=None)
    pi_id: Optional[int] = Field(default=None)
    pi_name: Optional[str] = Field(default=None)
    pi_email: Optional[str] = Field(default=None)
    position: PositionEnum
    content: Optional[dict] = Field(default=None)


class UserFormGet(BaseModel):
    email: Optional[EmailStr] = Field(default=None)
    pi_id: Optional[int] = Field(default=None)
    pi_name: Optional[str] = Field(default=None)
    pi_email: Optional[str] = Field(default=None)
    position: PositionEnum
    content: Optional[dict] = Field(default=None)


class UserFormPost(BaseModel):
    email: Optional[EmailStr] = Field(default=None)
    pi_id: Optional[int] = Field(default=None)
    pi_name: Optional[str] = Field(default=None)
    pi_email: Optional[str] = Field(default=None)
    position: PositionEnum

    # JSONB values for form v1
    how_chtc_can_help: str
    computing_type: str
    # Optional
    mentor_name: Optional[str] = Field(default=None)
    mentor_email: Optional[str] = Field(default=None)
    marketing_attribution: Optional[str] = Field(default=None)
    research_computing_area: Optional[str] = Field(default=None)
    software_link: Optional[str] = Field(default=None)
    cpu_cores: Optional[str] = Field(default=None)
    memory_gb: Optional[str] = Field(default=None)
    disk_space_gb: Optional[str] = Field(default=None)
    calculation_runtime_hours: Optional[str] = Field(default=None)
    gpu_type: Optional[str] = Field(default=None)
    calculation_quantity: Optional[str] = Field(default=None)
    special_access: Optional[str] = Field(default=None)
    extra_info: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def validate_pi_fields(self):
        has_pi_id = self.pi_id is not None
        has_pi_name = self.pi_name is not None
        has_pi_email = self.pi_email is not None

        if has_pi_id == (has_pi_name or has_pi_email):
            raise ValueError("Provide either pi_id or both pi_name and pi_email")

        if has_pi_name != has_pi_email:
            raise ValueError("pi_name and pi_email must be provided together")

        return self
