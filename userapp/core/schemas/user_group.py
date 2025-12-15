from userapp.core.schemas.general import BaseModel

class UserGroupBase(BaseModel):
    group_id: int
    user_id: int

class UserGroupCreate(UserGroupBase):
    pass

class UserGroupUpdate(UserGroupBase):
    pass

class UserGroup(UserGroupBase):
    id: int
