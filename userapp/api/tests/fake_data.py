from datetime import datetime
import random
from typing import Optional

from userapp.core.models.enum import RoleEnum, PositionEnum
from userapp.core.schemas.user_submit import UserSubmitPost


def project_data_f(
    name: Optional[str] = None,
    pi: Optional[int] = None,
    staff1: Optional[int] = None,
    staff2: Optional[int] = None,
    status: Optional[str] = None,
    access: Optional[str] = None,
    accounting_group: Optional[str] = None,
    url: Optional[str] = None,
    date: Optional[datetime] = None,
    ticket: Optional[int] = None,
    last_contact: Optional[datetime] = None
):
    rand = random.randint(100000, 999999)
    return {
        "name": name if name else f"test-project-{rand}",
        "pi": pi,
        "staff1": staff1,
        "staff2": staff2,
        "status": status,
        "access": access,
        "accounting_group": f"accounting-group-{rand}",
        "url": url if url else "http://example.com",
        "ticket": ticket,
        "last_contact": last_contact.isoformat() if last_contact else None
    }


def user_data_f(index: int, primary_project_id, is_admin=False) -> dict:
    """
    Generate a unique user payload for testing, based on the UserBase schema.
    """
    rand = random.randint(100000, 999999)
    return {
        "name": f"User {index}",
        "email1": f"testuser{rand}@example.com",
        "email2": f"altuser{rand}@example.com",
        "netid": f"netid{rand}",
        "netid_exp_datetime": datetime.now().isoformat(),
        "phone1": f"555-010{index}",
        "phone2": f"555-020{index}",
        "is_admin": is_admin,
        "active": True,
        "unix_uid": rand,
        "position": PositionEnum.GRAD_STUDENT.name,
        "primary_project_id": primary_project_id,
        "primary_project_role": RoleEnum.MEMBER.name,
        "submit_nodes": [
            {
                "submit_node_id": 1
            }
        ]
    }

def user_form_data_f() -> dict:

    rand = random.randint(100000, 999999)
    return {
        "pi_id": None,
        "pi_name": "John Doe",
        "pi_email": "johndoe@wisc.edu",
        "position": "POSTDOC",
        "how_chtc_can_help": "Research computing support",
        "computing_type": "High throughput computing",
        "mentor_name": f"Mentor {rand}",
        "mentor_email": f"cool-{rand}@gmail.com",
        "marketing_attribution": convert_to_none_sometimes(f"Cool attribution {rand}"),
        "research_computing_area": convert_to_none_sometimes(f"Cool attribution {rand}"),
        "software_link": convert_to_none_sometimes(f"Software Link {rand}"),
        "cpu_cores": convert_to_none_sometimes(f"CPU Cores {rand}"),
        "memory_gb": convert_to_none_sometimes(f"Memory GB {rand}"),
        "disk_space_gb": convert_to_none_sometimes(f"Disk Space GB {rand}"),
        "calculation_runtime_hours": convert_to_none_sometimes(f"calculation Runtime Hours {rand}"),
        "gpu_type": convert_to_none_sometimes(f"GPU Type {rand}"),
        "calculation_quantity": convert_to_none_sometimes(f"Calculation Quantity {rand}"),
        "special_access": convert_to_none_sometimes(f"Special Access {rand}"),
        "extra_info": convert_to_none_sometimes(f"Extra Info {rand}"),
    }


def user_form_approval_data_f(project_id: int, submit_nodes: list[UserSubmitPost]) -> dict:
    return {
        "status": "APPROVED",
        "project_id": project_id,
        "user_position": PositionEnum.GRAD_STUDENT.value,
        "submit_nodes": submit_nodes,
    }


def convert_to_none_sometimes(value: str, probability: float = .5) -> str | None:
    """Return None randomly based on given probability"""
    return value if random.random() < probability else None
