from sqlalchemy.orm import selectinload

from userapp.core.models.tables import User as UserTable, Note as NoteTable, Project as ProjectTable
from userapp.core.models.views import JoinedProjectView as JoinedProjectViewTable, UserGroupView as UserGroupViewTable

user_load_options = [
    selectinload(UserTable.notes).joinedload(NoteTable.author),
    selectinload(UserTable.groups).selectinload(UserGroupViewTable.point_of_contact_user),
    selectinload(UserTable.projects).selectinload(JoinedProjectViewTable.staff1_user),
    selectinload(UserTable.projects).selectinload(JoinedProjectViewTable.staff2_user),
    selectinload(UserTable.user_forms),
    selectinload(UserTable.submit_nodes)
]

# Project endpoints return ProjectGetFull and eager-load these relationships here
# (mirrors user_load_options for the user endpoints). ProjectGet is the light
# base, kept for embedding a project inside other schemas (like UserGet).
project_load_options = [
    selectinload(ProjectTable.college_and_department),
    selectinload(ProjectTable.field_of_science),
]
