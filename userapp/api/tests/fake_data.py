from datetime import datetime
import random
from typing import Optional

from userapp.core.models.enum import RoleEnum, PositionEnum


def project_data_f(
    name: Optional[str] = None,
    pi: Optional[int] = None,
    staff1: Optional[str] = None,
    staff2: Optional[str] = None,
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
        "is_admin": False,
        "active": False,
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