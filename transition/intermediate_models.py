
from userapp.core.models.tables import *

class User(Base):
    __tablename__ = 'users'
    __table_args__ = {'extend_existing': True}
    position = Column(Integer)
    netid = Column(String(255))

class UserProject(Base):
    __tablename__ = 'user_projects'
    __table_args__ = {'extend_existing': True}
    role = Column(Integer)
