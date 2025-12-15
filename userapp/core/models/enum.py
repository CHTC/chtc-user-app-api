from enum import Enum

class RoleEnum(Enum):
    MEMBER = "MEMBER"
    PI = "PI"

class PositionEnum(Enum):
    SELECT = "SELECT"
    FACULTY = "FACULTY"
    STAFF = "STAFF"
    POSTDOC = "POSTDOC"
    GRAD_STUDENT = "GRAD_STUDENT"
    UNDERGRADUATE = "UNDERGRADUATE"
    OTHER = "OTHER"
