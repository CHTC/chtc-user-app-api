from userapp.core.schemas.general import BaseModel

class SubmitNodeBase(BaseModel):
    name: str

class SubmitNodeCreate(SubmitNodeBase):
    pass

class SubmitNodeUpdate(SubmitNodeBase):
    pass

class SubmitNode(SubmitNodeBase):
    id: int
