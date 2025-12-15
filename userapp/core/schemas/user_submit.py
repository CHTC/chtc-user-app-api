from typing import Optional

from userapp.core.schemas.general import BaseModel

class UserSubmitBase(BaseModel):
    submit_node_id: int
    for_auth_netid: bool
    disk_quota: Optional[int] = None
    hpc_diskquota: Optional[int] = None
    hpc_inodequota: Optional[int] = None
    hpc_joblimit: Optional[int] = None
    hpc_corelimit: Optional[int] = None
    hpc_fairshare: Optional[int] = None

class UserSubmitCreate(UserSubmitBase):
    pass

class UserSubmitUpdate(UserSubmitBase):
    id: int

class UserSubmit(UserSubmitBase):
    id: int
    submit_node_name: str

class UserSubmitGetSlim(BaseModel):
    id: int
    submit_node_id: int
    submit_node_name: str
    for_auth_netid: bool
