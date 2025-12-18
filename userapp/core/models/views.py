from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy import Enum as SQLEnum

from userapp.core.models.enum import RoleEnum, PositionEnum
from userapp.core.models.main import Base


class PiProjectView(Base):
    __tablename__ = 'pi_projects'
    __table_args__ = {'info': dict(is_view=True)}
    user_id = Column(Integer, primary_key=True)
    username = Column(String(255))
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
    project_staff1 = Column(String(255))
    project_staff2 = Column(String(255))
    project_status = Column(String(255))
    project_last_contact = Column(TIMESTAMP)
    project_accounting_group = Column(String(255))
    is_primary = Column(Boolean)
    username = Column(String(255))
    name = Column(String(255))
    email1 = Column(String(255))
    email2 = Column(String(255))
    netid = Column(String(255)) # Should be unique post transition
    netid_exp_datetime = Column(TIMESTAMP)
    phone1 = Column(String(255))
    phone2 = Column(String(255))
    is_admin = Column(Boolean)
    auth_netid = Column(Boolean)
    auth_username = Column(Boolean)
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
