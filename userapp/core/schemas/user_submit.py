from typing import Optional

from pydantic import ConfigDict, Field

from userapp.core.schemas.general import BaseModel

class UserSubmitTableSchema(BaseModel):
    """Used to represent a user-submit node association as stored in the database"""

    model_config = ConfigDict(extra='ignore')

    id:  Optional[int] = Field(default=None)
    submit_node_id: int
    user_id: int
    for_auth_netid: bool
    disk_quota: Optional[int] = Field(default=None)
    hpc_diskquota: Optional[int] = Field(default=None)
    hpc_inodequota: Optional[int] = Field(default=None)
    hpc_joblimit: Optional[int] = Field(default=None)
    hpc_corelimit: Optional[int] = Field(default=None)
    hpc_fairshare: Optional[int] = Field(default=None)

class UserSubmitGet(BaseModel):

    model_config = ConfigDict(extra='ignore')

    id: Optional[int] = Field(default=None)
    submit_node_id: int
    submit_node_name: str
    user_id: int
    disk_quota: Optional[int] = Field(default=None)
    hpc_diskquota: Optional[int] = Field(default=None)
    hpc_inodequota: Optional[int] = Field(default=None)
    hpc_joblimit: Optional[int] = Field(default=None)
    hpc_corelimit: Optional[int] = Field(default=None)
    hpc_fairshare: Optional[int] = Field(default=None)

class UserSubmitPost(BaseModel):

    submit_node_id: int
    # for_auth_netid: bool # Gets handled automatically
    disk_quota: Optional[int] = Field(default=None)
    hpc_diskquota: Optional[int] = Field(default=None)
    hpc_inodequota: Optional[int] = Field(default=None)
    hpc_joblimit: Optional[int] = Field(default=None)
    hpc_corelimit: Optional[int] = Field(default=None)
    hpc_fairshare: Optional[int] = Field(default=None)
