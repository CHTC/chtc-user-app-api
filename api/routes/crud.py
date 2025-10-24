import api.schemas
import api.models
from api.crud import create_crud_router
from api.db import get_async_session

# Group
group_router = create_crud_router(
    session=get_async_session,
    name="groups",
    db_model=api.models.Group,
    get_schema=api.schemas.Group,
    create_schema=api.schemas.GroupCreate,
    update_schema=api.schemas.GroupUpdate
)

# Note
note_router = create_crud_router(
    session=get_async_session,
    name="notes",
    db_model=api.models.Note,
    get_schema=api.schemas.Note,
    create_schema=api.schemas.NoteCreate,
    update_schema=api.schemas.NoteUpdate
)

# PIProject
pi_project_router = create_crud_router(
    session=get_async_session,
    name="pi_projects",
    db_model=api.models.PIProject,
    get_schema=api.schemas.PIProject,
    create_schema=api.schemas.PIProjectCreate,
    update_schema=api.schemas.PIProjectUpdate
)

# Project
project_router = create_crud_router(
    session=get_async_session,
    name="projects",
    db_model=api.models.Project,
    get_schema=api.schemas.Project,
    create_schema=api.schemas.ProjectCreate,
    update_schema=api.schemas.ProjectUpdate
)

# SubmitNode
submit_node_router = create_crud_router(
    session=get_async_session,
    name="submit_nodes",
    db_model=api.models.SubmitNode,
    get_schema=api.schemas.SubmitNode,
    create_schema=api.schemas.SubmitNodeCreate,
    update_schema=api.schemas.SubmitNodeUpdate
)

# User
user_router = create_crud_router(
    session=get_async_session,
    name="users",
    db_model=api.models.User,
    get_schema=api.schemas.User,
    create_schema=api.schemas.UserCreate,
    update_schema=api.schemas.UserUpdate
)

# UserGroup
user_group_router = create_crud_router(
    session=get_async_session,
    name="user_groups",
    db_model=api.models.UserGroup,
    get_schema=api.schemas.UserGroup,
    create_schema=api.schemas.UserGroupCreate,
    update_schema=api.schemas.UserGroupUpdate
)

# UserNote
user_note_router = create_crud_router(
    session=get_async_session,
    name="user_notes",
    db_model=api.models.UserNote,
    get_schema=api.schemas.UserNote,
    create_schema=api.schemas.UserNoteCreate,
    update_schema=api.schemas.UserNoteUpdate
)

# UserProject
user_project_router = create_crud_router(
    session=get_async_session,
    name="user_projects",
    db_model=api.models.UserProject,
    get_schema=api.schemas.UserProject,
    create_schema=api.schemas.UserProjectCreate,
    update_schema=api.schemas.UserProjectUpdate
)

# UserSubmit
user_submit_router = create_crud_router(
    session=get_async_session,
    name="user_submits",
    db_model=api.models.UserSubmit,
    get_schema=api.schemas.UserSubmit,
    create_schema=api.schemas.UserSubmitCreate,
    update_schema=api.schemas.UserSubmitUpdate
)

# List of all routers for easy import
all_routers = [
    group_router,
    note_router,
    pi_project_router,
    project_router,
    submit_node_router,
    user_router,
    user_group_router,
    user_note_router,
    user_project_router,
    user_submit_router,
]
