from typing import List

from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, ForeignKey, UniqueConstraint, func, VARCHAR, \
    Table, Index
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy import Enum as SQLEnum

from userapp.core.models.enum import RoleEnum, PositionEnum, HttpRequestMethodEnum
from userapp.core.models.main import Base
from userapp.core.models.views import JoinedProjectView
from userapp.core.models.views import UserSubmitNodesView


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
    note = Column(Text, nullable=False)
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


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (
        UniqueConstraint('netid', name='uniq_netid_unique_if_not_null', postgresql_nulls_not_distinct=False),
    )

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True)
    name = Column(String(255), nullable=False)
    password = Column(String(255))
    email1 = Column(String(255), nullable=False)
    email2 = Column(String(255))
    netid = Column(String(255)) # Made unique via a Table constraint
    netid_exp_datetime = Column(TIMESTAMP)
    phone1 = Column(String(255))
    phone2 = Column(String(255))
    is_admin = Column(Boolean, default=False)
    active = Column(Boolean, default=False)
    date = Column(TIMESTAMP, nullable=False, server_default=func.now())
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

    submit_nodes: Mapped[List[UserSubmitNodesView]] = relationship(
        "UserSubmitNodesView",
        primaryjoin="User.id==foreign(UserSubmitNodesView.user_id)",
        lazy="joined",
        viewonly=True,
    )

    projects: Mapped[List["JoinedProjectView"]] = relationship(
        "JoinedProjectView",
        primaryjoin="User.id==foreign(JoinedProjectView.id)",
        lazy="joined",
        viewonly=True,
    )

    groups: Mapped[List["Group"]] = relationship(
        secondary="user_groups",
        primaryjoin="User.id==UserGroup.user_id",
        secondaryjoin="Group.id==UserGroup.group_id",
        foreign_keys="[UserGroup.user_id, UserGroup.group_id]",
        lazy="joined",
        backref="users"
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
    project_id = Column(Integer, ForeignKey('projects.id', ondelete="CASCADE"), nullable=False)
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
    __table_args__ = (UniqueConstraint('user_id', 'submit_node_id', 'for_auth_netid', name='user_submits_distinct'),)

class Token(Base):
    __tablename__ = 'tokens'
    id = Column(Integer, primary_key=True, index=True)
    created_by = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"))
    token = Column(String(255), unique=True, nullable=False)
    description = Column(String(255))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    expires_at = Column(TIMESTAMP)

    permissions: Mapped[List["TokenPermission"]] = relationship(
        "TokenPermission",
        cascade="all, delete-orphan",
        lazy="joined"
    )

class TokenPermission(Base):
    __tablename__ = 'token_permissions'
    __table_args__ = (
        Index('ix_token_permissions_token_id', 'token_id'),
        UniqueConstraint('token_id', 'method', 'route', name='token_permissions_distinct'),
    )
    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, ForeignKey('tokens.id', ondelete="CASCADE"), nullable=False)
    method = Column(SQLEnum(HttpRequestMethodEnum, name="http_request_method_enum"), nullable=False)
    route = Column(String(255), nullable=False)

class Access(Base):
    __tablename__ = 'access'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    token_id = Column(Integer, ForeignKey('tokens.id'), nullable=True)
    route = Column(String(255), nullable=False)
    payload = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    expires_at = Column(TIMESTAMP)
