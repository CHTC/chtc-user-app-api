from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy import Enum as SQLEnum

from userapp.core.models.enum import RoleEnum
from userapp.core.models.main import Base


class PiProjectView(Base):
    __tablename__ = 'pi_projects'
    __table_args__ = {'info': dict(is_view=True)}
    user_id = Column(Integer, primary_key=True)
    username = Column(String(255))
    name = Column(String(255))
    project_id = Column(Integer, primary_key=True)
    project_name = Column(String(255))


class JoinedProjectView(Base):
    __tablename__ = 'joined_projects'
    __table_args__ = {'info': dict(is_view=True)}
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


class UserSubmitNodesView(Base):
    __tablename__ = 'user_submit_nodes'
    __table_args__ = {'info': dict(is_view=True)}
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    submit_node_id = Column(Integer)
    submit_node_name = Column(String(60))
    for_auth_netid = Column(Boolean)
    disk_quota = Column(Integer)
    hpc_diskquota = Column(Integer)
    hpc_inodequota = Column(Integer)
    hpc_joblimit = Column(Integer)
    hpc_corelimit = Column(Integer)
    hpc_fairshare = Column(Integer)
