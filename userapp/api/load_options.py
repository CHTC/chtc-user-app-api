from sqlalchemy.orm import selectinload

from userapp.core.models.tables import User as UserTable, Note as NoteTable, Group as GroupTable
from userapp.core.models.views import JoinedProjectView as JoinedProjectViewTable

user_load_options = [
    selectinload(UserTable.notes).joinedload(NoteTable.author),
    selectinload(UserTable.groups).joinedload(GroupTable.point_of_contact_user),
    selectinload(UserTable.projects).selectinload(JoinedProjectViewTable.staff1_user),
    selectinload(UserTable.projects).selectinload(JoinedProjectViewTable.staff2_user),
    selectinload(UserTable.submit_nodes)
]
