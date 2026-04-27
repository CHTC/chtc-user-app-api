from typing import Optional

from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, relationship

from userapp.core.models.enum import RoleEnum, PositionEnum, FormTypeEnum, FormStatusEnum
from userapp.core.models.main import Base


class PiProjectView(Base):
    __tablename__ = 'pi_projects'
    __table_args__ = {'info': dict(is_view=True)}
    user_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    project_id = Column(Integer, primary_key=True)
    project_name = Column(String(255))
    email1 = Column(String(255))
    phone1 = Column(String(255))
    netid = Column(String(255))


class JoinedProjectView(Base):
    __tablename__ = 'joined_projects'
    __table_args__ = {'info': dict(is_view=True)}
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, primary_key=True)
    project_name = Column(String(255))
    project_staff1 = Column(Integer)
    project_staff2 = Column(Integer)
    project_status = Column(String(255))

    staff1_user: Mapped[Optional["User"]] = relationship(
        "User",
        primaryjoin="JoinedProjectView.project_staff1==foreign(User.id)",
        lazy="selectin",
        viewonly=True,
    )
    staff2_user: Mapped[Optional["User"]] = relationship(
        "User",
        primaryjoin="JoinedProjectView.project_staff2==foreign(User.id)",
        lazy="selectin",
        viewonly=True,
    )
    project_last_contact = Column(TIMESTAMP)
    project_accounting_group = Column(String(255))
    is_primary = Column(Boolean)
    name = Column(String(255))
    username = Column(String(255))
    email1 = Column(String(255))
    email2 = Column(String(255))
    netid = Column(String(255)) # Should be unique post transition
    netid_exp_datetime = Column(TIMESTAMP)
    phone1 = Column(String(255))
    phone2 = Column(String(255))
    is_admin = Column(Boolean)
    active = Column(Boolean)
    date = Column(TIMESTAMP)
    unix_uid = Column(Integer)
    position = Column(SQLEnum(PositionEnum, name="position_enum"))
    role = Column(SQLEnum(RoleEnum, name="role_enum"))
    last_note_ticket = Column(String(9))


class UserSubmitNodesView(Base):
    __tablename__ = 'user_submit_nodes'
    __table_args__ = {'info': dict(is_view=True)}
    user_id = Column(Integer, primary_key=True)
    submit_node_id = Column(Integer, primary_key=True)
    submit_node_name = Column(String(60))
    disk_quota = Column(Integer)
    hpc_diskquota = Column(Integer)
    hpc_inodequota = Column(Integer)
    hpc_joblimit = Column(Integer)
    hpc_corelimit = Column(Integer)
    hpc_fairshare = Column(Integer)


class UserApplicationView(Base):
    __tablename__ = 'user_applications'
    __table_args__ = {'info': dict(is_view=True)}

    # BaseForm columns
    id = Column(Integer, primary_key=True)
    form_type = Column(SQLEnum(FormTypeEnum, name="form_type_enum"))
    status = Column(SQLEnum(FormStatusEnum, name="form_status_enum"))
    created_by = Column(Integer)
    created_at = Column(TIMESTAMP)
    updated_by = Column(Integer)
    updated_at = Column(TIMESTAMP)

    # UserForm columns
    pi_id = Column(Integer)
    pi_name = Column(String(255))
    pi_email = Column(String(255))
    position = Column(SQLEnum(PositionEnum, name="position_enum"))
    content = Column(String)  # JSONB stored as text in view

    # Relationships for foreign keys
    created_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        primaryjoin="UserApplicationView.created_by==foreign(User.id)",
        lazy="selectin",
        viewonly=True,
        foreign_keys="[UserApplicationView.created_by]",
    )
    
    updated_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        primaryjoin="UserApplicationView.updated_by==foreign(User.id)",
        lazy="selectin",
        viewonly=True,
        foreign_keys="[UserApplicationView.updated_by]",
    )
    
    pi_user: Mapped[Optional["User"]] = relationship(
        "User",
        primaryjoin="UserApplicationView.pi_id==foreign(User.id)",
        lazy="selectin",
        viewonly=True,
        foreign_keys="[UserApplicationView.pi_id]",
    )
