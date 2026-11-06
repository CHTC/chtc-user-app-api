from typing import List, Optional

from sqlalchemy import BigInteger, CheckConstraint, Column, Integer, String, Boolean, Text, TIMESTAMP, ForeignKey, \
    UniqueConstraint, func, VARCHAR, \
    Table, Index, null
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

from userapp.core.models.enum import FormStatusEnum, FormTypeEnum, PositionEnum, HttpRequestMethodEnum, \
    EntityManagerEnum, AuditActionEnum
from userapp.core.models.main import Base
from userapp.core.models.views import JoinedProjectView
from userapp.core.models.views import UserSubmitView
from userapp.core.models.views import UserApplicationView
from userapp.core.models.views import UserGroupsView


class Group(Base):
    __tablename__ = 'groups'
    __table_args__ = (
        CheckConstraint('owner_group_id IS NULL OR owner_group_id <> id', name='ck_groups_not_self_owned'),
    )
    id = Column(Integer, primary_key=True, index=True)
    name = Column(VARCHAR(32), unique=True, nullable=False)
    unix_gid = Column(Integer, unique=True)
    # NULL means only staff administer the group
    owner_group_id = Column(Integer, ForeignKey('groups.id'), index=True)
    description = Column(Text)
    # Which system owns the group's user membership: a managed sync replaces it wholesale
    managed_by = Column(SQLEnum(EntityManagerEnum, name="entity_manager_enum"), nullable=False, server_default=EntityManagerEnum.APPLICATION.value)
    # Groups are never hard-deleted; see services.membership.delete_group
    deleted_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())


class GroupMember(Base):
    """A direct membership: exactly one of member_user_id / member_group_id is set"""
    __tablename__ = 'group_members'
    __table_args__ = (
        CheckConstraint('(member_user_id IS NULL) <> (member_group_id IS NULL)', name='ck_group_members_one_member'),
        CheckConstraint('member_group_id IS NULL OR member_group_id <> group_id', name='ck_group_members_not_self'),
        UniqueConstraint('group_id', 'member_user_id', name='group_members_user_distinct'),
        UniqueConstraint('group_id', 'member_group_id', name='group_members_group_distinct'),
        Index('ix_group_members_member_user_id', 'member_user_id'),
        Index('ix_group_members_member_group_id', 'member_group_id'),
    )
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)
    member_user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    member_group_id = Column(Integer, ForeignKey('groups.id', ondelete='CASCADE'))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

    member_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[member_user_id],
        lazy="selectin",
    )
    member_group: Mapped[Optional["Group"]] = relationship(
        "Group",
        foreign_keys=[member_group_id],
        lazy="selectin",
    )


class GroupEffectiveMember(Base):
    """Materialized flattening of group_members; rewritten by services.membership, never edited by hand"""
    __tablename__ = 'group_effective_members'
    __table_args__ = (
        Index('ix_group_effective_members_user_id', 'user_id'),
        Index('ix_group_effective_members_path', 'path', postgresql_using='gin'),
        CheckConstraint('cardinality(path) >= 1 AND path[1] = group_id',
                        name='ck_group_effective_members_path_root'),
    )
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='CASCADE'), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    # Group ids from group_id down to the group the user is a direct member of
    path = Column(ARRAY(Integer), primary_key=True)


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
    display_name = Column(String(255))
    description = Column(Text)
    pi_group_id = Column(Integer, ForeignKey('groups.id'), index=True)
    project_group_id = Column(Integer, ForeignKey('groups.id'), index=True)
    staff1 = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), index=True)
    staff2 = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), index=True)
    status = Column(String(255), index=True)
    access = Column(String(255))
    accounting_group = Column(String(255), nullable=False, index=True)
    url = Column(String(255))
    date = Column(TIMESTAMP, nullable=False, server_default=func.now())
    ticket = Column(Integer)
    last_contact = Column(TIMESTAMP)
    college_and_department_id = Column(Integer, ForeignKey('college_and_departments.id', ondelete='SET NULL'), index=True)
    fos_id = Column(String(16), ForeignKey('fields_of_science.fos_id', ondelete='SET NULL'), index=True)

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
    college_and_department: Mapped[Optional["CollegeAndDepartment"]] = relationship(
        "CollegeAndDepartment",
        lazy="select",
    )
    field_of_science: Mapped[Optional["FieldsOfScience"]] = relationship(
        "FieldsOfScience",
        lazy="select",
    )

class CollegeAndDepartment(Base):
    __tablename__ = 'college_and_departments'
    # (college, department) is the natural key; the surrogate id is only stable within
    # one database, so the pair is what identifies a row across environments.
    __table_args__ = (
        UniqueConstraint('college', 'department', name='uq_college_and_departments_college_department'),
    )
    id = Column(Integer, primary_key=True)
    college = Column(String(255))
    department = Column(String(255))

class FieldsOfScience(Base):
    __tablename__ = 'fields_of_science'
    fos_id = Column(String(16), primary_key=True)
    sed_cip_title = Column(String(255))
    broad_field = Column(String(255))
    major_field = Column(String(255))
    detailed_field = Column(String(255))

class SubmitNode(Base):
    __tablename__ = 'submit_nodes'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(60))
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='SET NULL'), index=True)


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
    username = Column(String(255), unique=True)
    netid_exp_datetime = Column(TIMESTAMP)
    phone1 = Column(String(255))
    phone2 = Column(String(255))
    is_admin = Column(Boolean, default=False)
    active = Column(Boolean, nullable=False, server_default='false')
    date = Column(TIMESTAMP, nullable=False, server_default=func.now()) # TODO: Delete this after we have migrated to created_at
    unix_uid = Column(Integer)
    position = Column(SQLEnum(PositionEnum, name="position_enum"), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    # Need not reference a current membership: it survives removal from the project's group
    primary_project_id = Column(Integer, ForeignKey('projects.id', ondelete='SET NULL'), index=True)

    notes: Mapped[List["Note"]] = relationship(
        secondary="user_notes",
        primaryjoin="User.id==UserNote.user_id",
        secondaryjoin="Note.id==UserNote.note_id",
        foreign_keys="[UserNote.user_id, UserNote.note_id]",
        lazy="selectin",
        back_populates="users"
    )

    submit_nodes: Mapped[List[UserSubmitView]] = relationship(
        "UserSubmitView",
        primaryjoin="User.id==foreign(UserSubmitView.user_id)",
        lazy="selectin",
        viewonly=True,
    )

    projects: Mapped[List["JoinedProjectView"]] = relationship(
        "JoinedProjectView",
        primaryjoin="User.id==foreign(JoinedProjectView.id)",
        lazy="selectin",
        viewonly=True,
    )

    groups: Mapped[List["UserGroupsView"]] = relationship(
        "UserGroupsView",
        primaryjoin="User.id==foreign(UserGroupsView.user_id)",
        lazy="selectin",
        viewonly=True,
    )

    user_forms: Mapped[List[UserApplicationView]] = relationship(
        "UserApplicationView",
        primaryjoin="User.id==foreign(UserApplicationView.created_by)",
        lazy="selectin",
        viewonly=True,
    )


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


class AuditLog(Base):
    """Append-only: nothing in the application updates or deletes these rows"""
    __tablename__ = 'audit_log'
    __table_args__ = (
        Index('ix_audit_log_group_id', 'group_id'),
        Index('ix_audit_log_actor_id', 'actor_id'),
        Index('ix_audit_log_member_user_id', 'member_user_id'),
        Index('ix_audit_log_occurred_at', 'occurred_at'),
    )
    id = Column(BigInteger, primary_key=True)
    occurred_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    actor_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    action = Column(SQLEnum(AuditActionEnum, name="audit_action_enum"), nullable=False)
    group_id = Column(Integer, ForeignKey('groups.id'))
    member_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    member_group_id = Column(Integer, ForeignKey('groups.id'))
    caused_by = Column(BigInteger, ForeignKey('audit_log.id'))
    details = Column(JSONB)

    # Read-only: the log is written through services.audit.log with plain ids
    actor: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[actor_id], lazy="selectin", viewonly=True)
    member_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[member_user_id], lazy="selectin", viewonly=True)
    member_group: Mapped[Optional["Group"]] = relationship(
        "Group", foreign_keys=[member_group_id], lazy="selectin", viewonly=True)
