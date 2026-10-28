"""add Radiation Medicine to college_and_departments

Revision ID: e5b1d9a7c3f4
Revises: a3c8e5f1b9d2
Create Date: 2026-10-28 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b1d9a7c3f4'
down_revision: Union[str, Sequence[str], None] = 'a3c8e5f1b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# These rows are also appended to alembic/data/colleges_and_departments.csv so a
# fresh database seeded by 36df1f56cb9e already has them. The insert below is
# therefore a no-op on a fresh database and only adds rows to databases that were
# seeded before the CSV change. ON CONFLICT relies on the (college, department)
# unique constraint uq_college_and_departments_college_department.
NEW_ROWS = [
    ('School of Medicine and Public Health', 'Radiation Medicine'),
]


def upgrade() -> None:
    """Upgrade schema."""
    insert = sa.text(
        'INSERT INTO college_and_departments (college, department) '
        'VALUES (:college, :department) '
        'ON CONFLICT (college, department) DO NOTHING'
    )
    for college, department in NEW_ROWS:
        op.execute(insert.bindparams(college=college, department=department))


def downgrade() -> None:
    """Downgrade schema."""
    # projects.college_and_department_id is ON DELETE SET NULL, so any project
    # assigned to one of these departments loses that assignment on downgrade.
    delete = sa.text(
        'DELETE FROM college_and_departments '
        'WHERE college = :college AND department = :department'
    )
    for college, department in NEW_ROWS:
        op.execute(delete.bindparams(college=college, department=department))
