"""Basic forms

Revision ID: f91affa16676
Revises: b8ae04f033ae
Create Date: 2026-03-31 12:50:41.854864

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f91affa16676'
down_revision: Union[str, Sequence[str], None] = 'b8ae04f033ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


form_type_enum = postgresql.ENUM('USER', 'PROJECT', name='form_type_enum', create_type=False)
form_status_enum = postgresql.ENUM('PENDING', 'APPROVED', 'DENIED', name='form_status_enum', create_type=False)
position_enum = postgresql.ENUM(
    'SELECT',
    'FACULTY',
    'STAFF',
    'POSTDOC',
    'GRAD_STUDENT',
    'UNDERGRADUATE',
    'OTHER',
    name='position_enum',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    form_type_enum.create(bind, checkfirst=True)
    form_status_enum.create(bind, checkfirst=True)
    position_enum.create(bind, checkfirst=True)

    op.create_table(
        'forms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('form_type', form_type_enum, nullable=False),
        sa.Column('status', form_status_enum, server_default='PENDING', nullable=False),
        sa.Column('created_by', sa.Integer()),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_by', sa.Integer()),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_forms_id'), 'forms', ['id'], unique=False)

    op.create_table(
        'user_form',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pi_id', sa.Integer(), nullable=True),
        sa.Column('pi_name', sa.String(length=255), nullable=True),
        sa.Column('pi_email', sa.String(length=255), nullable=True),
        sa.Column('position', position_enum, nullable=True),
        sa.CheckConstraint(
            '((pi_id IS NOT NULL AND (pi_name IS NULL AND pi_email IS NULL)) OR (pi_id IS NULL AND (pi_name IS NOT NULL AND pi_email IS NOT NULL)))',
            name='ck_user_form_pi_info',
        ),
        sa.ForeignKeyConstraint(['id'], ['forms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pi_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index('idx_user_notes_userid_noteid_desc', 'user_notes', ['user_id', 'note_id'], unique=False, postgresql_using='btree')
    op.create_index('idx_user_notes_userid_projectid_noteid', 'user_notes', ['user_id', 'project_id', 'note_id'], unique=False)
    op.create_index(
        'idx_user_submits_userid_submitnodeid_incl',
        'user_submits',
        ['user_id', 'submit_node_id'],
        unique=False,
        postgresql_include=['disk_quota', 'hpc_diskquota', 'hpc_inodequota', 'hpc_joblimit', 'hpc_corelimit', 'hpc_fairshare'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'idx_user_submits_userid_submitnodeid_incl',
        table_name='user_submits',
        postgresql_include=['disk_quota', 'hpc_diskquota', 'hpc_inodequota', 'hpc_joblimit', 'hpc_corelimit', 'hpc_fairshare'],
    )
    op.drop_index('idx_user_notes_userid_projectid_noteid', table_name='user_notes')
    op.drop_index('idx_user_notes_userid_noteid_desc', table_name='user_notes', postgresql_using='btree')
    op.drop_table('user_form')
    op.drop_index(op.f('ix_forms_id'), table_name='forms')
    op.drop_table('forms')

    bind = op.get_bind()
    form_status_enum.drop(bind, checkfirst=True)
    form_type_enum.drop(bind, checkfirst=True)
