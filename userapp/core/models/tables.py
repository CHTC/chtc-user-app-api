from typing import List, Optional

from sqlalchemy import CheckConstraint, Column, Integer, String, Boolean, Text, TIMESTAMP, ForeignKey, UniqueConstraint, \
    func, VARCHAR, \
    Table, Index, null
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB

from userapp.core.models.enum import FormStatusEnum, FormTypeEnum, RoleEnum, PositionEnum, HttpRequestMethodEnum
from userapp.core.models.main import Base
from userapp.core.models.views import JoinedProjectView
from userapp.core.models.views import UserSubmitNodesView
from userapp.core.models.views import UserApplicationView


class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(VARCHAR(32), unique=True, nullable=False)
    point_of_contact = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), index=True)
    unix_gid = Column(Integer, unique=True)
    has_groupdir = Column(Boolean, nullable=False, default=True)

    point_of_contact_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[point_of_contact],
        lazy="selectin",
    )


class Note(Base):
    __tablename__ = 'notes'
    id = Column(Integer, primary_key=True, index=True)
    ticket = Column(String(9))
    note = Column(Text, nullable=False)
    author_id = Column('author', Integer, ForeignKey('users.id', ondelete='SET NULL'), index=True)
    date = Column(TIMESTAMP, nullable=False, server_default=func.now())

    # Relationships
    author: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[author_id],
        lazy="selectin",
    )
    users: Mapped[List["User"]] = relationship(
        secondary="user_notes",
        primaryjoin="Note.id==UserNote.note_id",
        secondaryjoin="User.id==UserNote.user_id",
        foreign_keys="[UserNote.note_id, UserNote.user_id]",
        lazy="selectin",
        back_populates="notes"
    )


class Project(Base):
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    pi = Column(Integer, index=True)
    staff1 = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), index=True)
    staff2 = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), index=True)
    status = Column(String(255), index=True)
    access = Column(String(255))
    accounting_group = Column(String(255), nullable=False, index=True)
    url = Column(String(255))
    date = Column(TIMESTAMP, nullable=False, server_default=func.now())
    ticket = Column(Integer)
    last_contact = Column(TIMESTAMP)

    staff1_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[staff1],
        lazy="selectin",
    )
    staff2_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[staff2],
        lazy="selectin",
    )


class SubmitNode(Base):
    __tablename__ = 'submit_nodes'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(60))


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (
        UniqueConstraint('netid', name='uniq_netid_unique_if_not_null', postgresql_nulls_not_distinct=False),
        Index('ix_users_email1', 'email1'),
        Index('ix_users_unix_uid', 'unix_uid'),
        Index('ix_users_active', 'active'),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email1 = Column(String(255))
    email2 = Column(String(255))
    netid = Column(String(255)) # Made unique via a Table constraint
    username = Column(String(255), unique=True, nullable=False)
    netid_exp_datetime = Column(TIMESTAMP)
    phone1 = Column(String(255))
    phone2 = Column(String(255))
    is_admin = Column(Boolean, default=False)
    active = Column(Boolean, nullable=False, server_default='false')
    date = Column(TIMESTAMP, nullable=False, server_default=func.now())
    unix_uid = Column(Integer)
    position = Column(SQLEnum(PositionEnum, name="position_enum"), nullable=True)

    notes: Mapped[List["Note"]] = relationship(
        secondary="user_notes",
        primaryjoin="User.id==UserNote.user_id",
        secondaryjoin="Note.id==UserNote.note_id",
        foreign_keys="[UserNote.user_id, UserNote.note_id]",
        lazy="selectin",
        back_populates="users"
    )

    submit_nodes: Mapped[List[UserSubmitNodesView]] = relationship(
        "UserSubmitNodesView",
        primaryjoin="User.id==foreign(UserSubmitNodesView.user_id)",
        lazy="selectin",
        viewonly=True,
    )

    projects: Mapped[List["JoinedProjectView"]] = relationship(
        "JoinedProjectView",
        primaryjoin="User.id==foreign(JoinedProjectView.id)",
        lazy="selectin",
        viewonly=True,
    )

    groups: Mapped[List["Group"]] = relationship(
        secondary="user_groups",
        primaryjoin="User.id==UserGroup.user_id",
        secondaryjoin="Group.id==UserGroup.group_id",
        foreign_keys="[UserGroup.user_id, UserGroup.group_id]",
        lazy="selectin",
        backref="users"
    )

    user_forms: Mapped[List[UserApplicationView]] = relationship(
        "UserApplicationView",
        primaryjoin="User.id==foreign(UserApplicationView.created_by)",
        lazy="selectin",
        viewonly=True,
    )


class UserGroup(Base):
    __tablename__ = 'user_groups'
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint('user_id', 'group_id', name='user_groups_distinct'),)


class UserNote(Base):
    __tablename__ = 'user_notes'
    __table_args__ = (
        Index('idx_user_notes_userid_projectid_noteid', 'user_id', 'project_id', 'note_id'),
        Index('idx_user_notes_userid_noteid_desc', 'user_id', 'note_id', postgresql_using='btree'),
        Index('ix_user_notes_note_id', 'note_id'),
        Index('ix_user_notes_project_id', 'project_id'),
    )
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete="CASCADE"), nullable=False)
    note_id = Column(Integer, ForeignKey('notes.id', ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"))


class UserProject(Base):
    __tablename__ = 'user_projects'
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    role = Column(SQLEnum(RoleEnum, name="role_enum"), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint('user_id', 'project_id', name='user_projects_distinct'),)


class UserSubmit(Base):
    __tablename__ = 'user_submits'
    __table_args__ = (
        UniqueConstraint('user_id', 'submit_node_id', 'for_auth_netid', name='user_submits_distinct'),
        Index('idx_user_submits_userid_submitnodeid_incl', 'user_id', 'submit_node_id',
              postgresql_include=['disk_quota', 'hpc_diskquota', 'hpc_inodequota', 'hpc_joblimit', 'hpc_corelimit', 'hpc_fairshare']),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    submit_node_id = Column(Integer, ForeignKey('submit_nodes.id', ondelete="CASCADE"), nullable=False, index=True)
    for_auth_netid = Column(Boolean)
    disk_quota = Column(Integer)
    hpc_diskquota = Column(Integer, nullable=False, default=100)
    hpc_inodequota = Column(Integer, nullable=False, default=50000)
    hpc_joblimit = Column(Integer, nullable=False, default=10)
    hpc_corelimit = Column(Integer, nullable=False, default=720)
    hpc_fairshare = Column(Integer, nullable=False, default=100)

class Token(Base):
    __tablename__ = 'tokens'
    id = Column(Integer, primary_key=True, index=True)
    created_by = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), index=True)
    token = Column(String(255), unique=True, nullable=False)
    description = Column(String(255))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    expires_at = Column(TIMESTAMP, index=True)

    permissions: Mapped[List["TokenPermission"]] = relationship(
        "TokenPermission",
        cascade="all, delete-orphan",
        lazy="selectin"
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
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    token_id = Column(Integer, ForeignKey('tokens.id'), nullable=True, index=True)
    route = Column(String(255), nullable=False)
    payload = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    expires_at = Column(TIMESTAMP)


class BaseForm(Base):
    __tablename__ = 'forms'
    id = Column(Integer, primary_key=True, index=True)
    form_type = Column(SQLEnum(FormTypeEnum, name="form_type_enum"), nullable=False, index=True)
    status = Column(SQLEnum(FormStatusEnum, name="form_status_enum"), nullable=False, server_default=FormStatusEnum.PENDING.value, index=True)
    created_by = Column(Integer, ForeignKey('users.id', ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_by = Column(Integer, ForeignKey('users.id', ondelete="SET NULL"), nullable=True, index=True)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    created_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="selectin",
    )

    updated_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[updated_by],
        lazy="selectin",
    )

class UserForm(Base):
    __tablename__ = 'user_form'
    id = Column(Integer, ForeignKey('forms.id', ondelete="CASCADE"), primary_key=True)

    # These can be tied into the existing data system
    email = Column(String(255), nullable=True)
    pi_id = Column(Integer, ForeignKey('users.id', ondelete="SET NULL"), nullable=True, index=True)
    pi_name = Column(String(255), nullable=True)
    pi_email = Column(String(255), nullable=True)
    position = Column(SQLEnum(PositionEnum, name="position_enum"), nullable=True)

    # This content cannot, things like "What is your favorite OS?"
    content = Column(JSONB, nullable=True, default=None)

    base_form: Mapped["BaseForm"] = relationship(
        "BaseForm",
        lazy="selectin",
    )

    # must either provide (pi_id) or (pi_name and pi_email) but not both
    __table_args__ = (
        CheckConstraint("((pi_id IS NOT NULL AND (pi_name IS NULL AND pi_email IS NULL)) OR (pi_id IS NULL AND (pi_name IS NOT NULL AND pi_email IS NOT NULL)))", name="ck_user_form_pi_info"),
    )
