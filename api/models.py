from enum import Enum
from typing import List

from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, ForeignKey, UniqueConstraint, func, VARCHAR, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, relationship
from sqlalchemy import Enum as SQLEnum, exists, and_
from sqlalchemy.ext.hybrid import hybrid_property


class Base(DeclarativeBase):
    pass


class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(VARCHAR(32), unique=True, nullable=False)
    point_of_contact = Column(String(50))
    unix_gid = Column(Integer, unique=True)
    has_groupdir = Column(Boolean, nullable=False, default=True)


class Note(Base):
    __tablename__ = 'notes'
    id = Column(Integer, primary_key=True, index=True)
    ticket = Column(String(9))
    note = Column(Text)
    author = Column(String(255))
    date = Column(TIMESTAMP, nullable=False, server_default=func.now())

    # Relationships
    users: Mapped[List["User"]] = relationship(
        secondary="user_notes",
        primaryjoin="Note.id==UserNote.note_id",
        secondaryjoin="User.id==UserNote.user_id",
        foreign_keys="[UserNote.note_id, UserNote.user_id]",
        lazy="joined",
        back_populates="notes"
    )


class Project(Base):
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    pi = Column(Integer)
    staff1 = Column(String(255))
    staff2 = Column(String(255))
    status = Column(String(255))
    access = Column(String(255))
    accounting_group = Column(String(255), nullable=False)
    url = Column(String(255))
    date = Column(TIMESTAMP, nullable=False, server_default=func.now())
    ticket = Column(Integer)
    last_contact = Column(TIMESTAMP)


class SubmitNode(Base):
    __tablename__ = 'submit_nodes'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(60))


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


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255))
    name = Column(String(255))
    password = Column(String(255))
    email1 = Column(String(255))
    email2 = Column(String(255))
    netid = Column(String(255))
    netid_exp_datetime = Column(TIMESTAMP)
    phone1 = Column(String(255))
    phone2 = Column(String(255))
    is_admin = Column(Boolean)
    auth_netid = Column(Boolean)
    auth_username = Column(Boolean)
    date = Column(TIMESTAMP, nullable=False)
    unix_uid = Column(Integer)
    position = Column(SQLEnum(PositionEnum, name="position_enum"), nullable=True)

    notes: Mapped[List["Note"]] = relationship(
        secondary="user_notes",
        primaryjoin="User.id==UserNote.user_id",
        secondaryjoin="Note.id==UserNote.note_id",
        foreign_keys="[UserNote.user_id, UserNote.note_id]",
        lazy="joined",
        back_populates="users"
    )


class UserGroup(Base):
    __tablename__ = 'user_groups'
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint('user_id', 'group_id', name='user_groups_distinct'),)


class UserNote(Base):
    __tablename__ = 'user_notes'
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey('notes.id', ondelete="CASCADE"))
    note_id = Column(Integer, ForeignKey('notes.id', ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"))


class UserProject(Base):
    __tablename__ = 'user_projects'
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    role = Column(SQLEnum(RoleEnum, name="role_enum"), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint('user_id', 'project_id', name='user_projects_distinct'),)


class UserSubmit(Base):
    __tablename__ = 'user_submits'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    submit_node_id = Column(Integer, ForeignKey('submit_nodes.id', ondelete="CASCADE"), nullable=False)
    for_auth_netid = Column(Boolean)
    disk_quota = Column(Integer)
    hpc_diskquota = Column(Integer, nullable=False, default=100)
    hpc_inodequota = Column(Integer, nullable=False, default=50000)
    hpc_joblimit = Column(Integer, nullable=False, default=10)
    hpc_corelimit = Column(Integer, nullable=False, default=720)
    hpc_fairshare = Column(Integer, nullable=False, default=100)
    __table_args__ = (UniqueConstraint('user_id', 'submit_node_id', name='user_submits_distinct'),)


class PiProjectView(Base):
    __tablename__ = 'pi_projects'
    user_id = Column(Integer, primary_key=True)
    username = Column(String(255))
    name = Column(String(255))
    project_id = Column(Integer, primary_key=True)
    project_name = Column(String(255))


class FullProjectView(Base):
    __tablename__ = 'full_projects'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    pi = Column(Integer)
    staff1 = Column(String(255))
    staff2 = Column(String(255))
    status = Column(String(255))
    access = Column(String(255))
    accounting_group = Column(String(255))
    url = Column(String(255))
    date = Column(TIMESTAMP)
    ticket = Column(Integer)
    last_contact = Column(TIMESTAMP)
    user_id = Column(Integer)
    username = Column(String(255))
    user_name = Column(String(255))
    role = Column(SQLEnum(RoleEnum, name="role_enum"))
    is_primary = Column(Boolean)


class JoinedProjectView(Base):
    __tablename__ = 'joined_projects'
    user_id = Column(Integer, primary_key=True)
    username = Column(String(255))
    email1 = Column(String(255))
    phone1 = Column(String(255))
    netid = Column(String(255))
    user_name = Column(String(255))
    project_id = Column(Integer, primary_key=True)
    project_name = Column(String(255))
    role = Column(SQLEnum(RoleEnum, name="role_enum"))
    last_note_ticket = Column(String(9))
