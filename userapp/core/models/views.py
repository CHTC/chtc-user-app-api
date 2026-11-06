from typing import Optional

from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, relationship

from userapp.core.models.enum import PositionEnum, FormTypeEnum, FormStatusEnum, EntityManagerEnum
from userapp.core.models.main import Base


class PiProjectView(Base):
    __tablename__ = 'pi_projects'
    __table_args__ = {'info': dict(is_view=True)}
    user_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    project_id = Column(Integer, primary_key=True)
    project_name = Column(String(255))
    project_display_name = Column(String(255))
    email1 = Column(String(255))
    phone1 = Column(String(255))
    netid = Column(String(255))


class JoinedProjectView(Base):
    __tablename__ = 'joined_projects'
    __table_args__ = {'info': dict(is_view=True)}
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, primary_key=True)
    project_name = Column(String(255))
    project_display_name = Column(String(255))
    project_staff1 = Column(Integer)
    project_staff2 = Column(Integer)
    project_status = Column(String(255))
    project_pi_group_id = Column(Integer)
    project_project_group_id = Column(Integer)

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

    # From the direct membership in the project group, NULL when access is only through another group
    direct = Column(Boolean)
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)
    is_primary = Column(Boolean)
    is_pi = Column(Boolean)

    # From the User
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
    last_note_ticket = Column(String(9))


class UserSubmitView(Base):
    """Submit nodes a user has access to, derived from group membership
    (a user has access to a submit node iff they belong to submit_nodes.group_id)."""
    __tablename__ = 'user_submit_nodes'
    __table_args__ = {'info': dict(is_view=True)}

    # No ForeignKey declarations — this is a view; FK constraints don't exist on it.
    user_id = Column(Integer, primary_key=True)

    # Legacy names for the two columns below, kept so existing consumers of this view - and
    # anything filtering /users/{id}/submit_nodes on them - keep working.
    submit_node_id = Column(Integer)
    submit_node_name = Column(String(60))

    # From SubmitNode
    id = Column(Integer, primary_key=True)
    name = Column(String(60))
    group_id = Column(Integer)


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
    email = Column(String(255))
    pi_id = Column(Integer)
    pi_name = Column(String(255))
    pi_email = Column(String(255))
    position = Column(SQLEnum(PositionEnum, name="position_enum"))
    content = Column(String)  # JSONB stored as text in view

    # From the requester's User row, so the list can be filtered on who submitted it
    created_by_name = Column(String(255))
    created_by_netid = Column(String(255))
    created_by_email1 = Column(String(255))

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


class GroupMembersView(Base):
    """Every user with access through a known group, and how (the members table of every access page)"""
    __tablename__ = 'group_members_view'
    __table_args__ = {'info': dict(is_view=True)}

    # No ForeignKey declarations — this is a view; FK constraints don't exist on it.
    group_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, primary_key=True)
    direct = Column(Boolean)
    # Every path from the group to the user, shortest first, as group ids and as group names
    paths = Column(JSONB)
    path_names = Column(JSONB)

    # From User
    name = Column(String(255))
    netid = Column(String(255))
    username = Column(String(255))
    email1 = Column(String(255))
    is_admin = Column(Boolean)
    active = Column(Boolean)
    unix_uid = Column(Integer)
    position = Column(SQLEnum(PositionEnum, name="position_enum"))


class UserGroupsView(Base):
    """Every group a known user is an effective member of, and how"""
    __tablename__ = 'user_groups_view'
    __table_args__ = {'info': dict(is_view=True)}

    # No ForeignKey declarations — this is a view; FK constraints don't exist on it.
    user_id = Column(Integer, primary_key=True)
    group_id = Column(Integer, primary_key=True)
    direct = Column(Boolean)
    paths = Column(JSONB)
    path_names = Column(JSONB)
    # The user administers the group (effective member of its owner group)
    is_owner = Column(Boolean)
    managed_by = Column(SQLEnum(EntityManagerEnum, name="entity_manager_enum"))

    # From Group
    name = Column(String(255))
    unix_gid = Column(Integer)
    owner_group_id = Column(Integer)
    description = Column(String)
    deleted_at = Column(TIMESTAMP)
