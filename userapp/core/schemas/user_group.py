from userapp.core.schemas.general import BaseModel

class UserGroupPost(BaseModel):
    group_id: int
    user_id: int
