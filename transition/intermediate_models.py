from typing import List

from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, ForeignKey, UniqueConstraint, func, VARCHAR, Table
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy import Enum as SQLEnum

from userapp.core.models.enum import RoleEnum, PositionEnum
from userapp.core.models.main import Base
from userapp.core.models.views import UserSubmitNodesView
from userapp.core.models.tables import *

class User(Base):
    __tablename__ = 'users'
    __table_args__ = {'extend_existing': True}
    position = Column(Integer)

class UserProject(Base):
    __tablename__ = 'user_projects'
    __table_args__ = {'extend_existing': True}
    role = Column(Integer)