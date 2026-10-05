"""add Center for Limnology and CHTC to college_and_departments

Revision ID: c7d2e4f8a1b6
Revises: 9b4e17c2d0a3
Create Date: 2026-10-05 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d2e4f8a1b6'
down_revision: Union[str, Sequence[str], None] = '9b4e17c2d0a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# These rows are also appended to alembic/data/colleges_and_departments.csv so a
# fresh database seeded by 36df1f56cb9e already has them. The insert below is
# therefore a no-op on a fresh database and only adds rows to databases that were
# seeded before the CSV change. ON CONFLICT relies on the (college, department)
# unique constraint uq_college_and_departments_college_department.
NEW_ROWS = [
    ('College of Letters & Science', 'Center for Limnology'),
    ('College of Computing & Artificial Intelligence (CAI)', 'Center for High Throughput Computing'),
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
