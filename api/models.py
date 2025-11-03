from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, ForeignKey, UniqueConstraint, func, VARCHAR
from sqlalchemy.orm import DeclarativeBase


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


class PIProject(Base):
    __tablename__ = 'pi_projects'
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer)
    pi_id = Column(Integer)


class Project(Base):
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True)
    pi = Column(Integer)
    staff1 = Column(String(255))
    staff2 = Column(String(255))
    status = Column(String(255))
    access = Column(String(255))
    accounting_group = Column(String(255))
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
    position = Column(Boolean)


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
    role = Column(Integer)
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
