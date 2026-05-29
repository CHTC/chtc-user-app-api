"""add group type/description and submit node groups

Revision ID: 026216ef4d8a
Revises: f2ec55925c4c
Create Date: 2026-05-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "026216ef4d8a"
down_revision: Union[str, None] = "f2ec55925c4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GROUPS_DATA = [
    {"node_name": "wright-ap4000.chtc.wisc.edu", "group_name": "wright-ap-login", "description": "Access to wright-ap4000.chtc.wisc.edu"},
    {"node_name": "townsend-submit.chtc.wisc.edu", "group_name": "townsend-ap-login", "description": "Access to townsend-submit.chtc.wisc.edu"},
    {"node_name": "hpclogin1.chtc.wisc.edu", "group_name": "spark-login", "description": "Access to hpclogin1.chtc.wisc.edu"},
    {"node_name": "osg-sw-submit.chtc.wisc.edu", "group_name": "osgsw-ap-login", "description": "Access to osg-sw-submit.chtc.wisc.edu"},
    {"node_name": "oconnor-ap.chtc.wisc.edu", "group_name": "oconnor-ap-login", "description": "Access to oconnor-ap.chtc.wisc.edu"},
    {"node_name": "learn.chtc.wisc.edu", "group_name": "learn-ap-login", "description": "Access to learn.chtc.wisc.edu"},
    {"node_name": "htc_transfer", "group_name": "htc-transfer-login", "description": "Access to htc_transfer"},
    {"node_name": "ap2002.chtc.wisc.edu", "group_name": "ap2002-login", "description": "Access to ap2002.chtc.wisc.edu"},
    {"node_name": "ap2001.chtc.wisc.edu", "group_name": "ap2001-login", "description": "Access to ap2001.chtc.wisc.edu"},
]


group_type_enum = postgresql.ENUM(
  "SUBMIT_NODE",
  name="group_type_enum",
  create_type=False,
)


def upgrade() -> None:
  bind = op.get_bind()
  group_type_enum.create(bind, checkfirst=True)
  op.add_column("groups", sa.Column("description", sa.String(length=255), nullable=True))
  op.add_column("groups", sa.Column("type", group_type_enum, nullable=True))

  for group in GROUPS_DATA:
    bind.execute(
      sa.text("""
        INSERT INTO groups (
          name,
          description,
          type,
          has_groupdir
        )
        VALUES (
          :name,
          :description,
          'SUBMIT_NODE'::group_type_enum,
          false
        )
        ON CONFLICT (name) DO NOTHING
      """),
      {
        "name": group["group_name"],
        "description": group["description"],
      },
    )

  mapping_params = {}
  mapping_placeholders = []

  for index, group in enumerate(GROUPS_DATA):
    node_key = f"node_name_{index}"
    group_key = f"group_name_{index}"

    mapping_placeholders.append(f"(:{node_key}, :{group_key})")

    mapping_params[node_key] = group["node_name"]
    mapping_params[group_key] = group["group_name"]

  mapping_sql = ", ".join(mapping_placeholders)

  bind.execute(
    sa.text(f"""
      INSERT INTO user_groups (
        user_id,
        group_id,
        managed_by
      )
      SELECT DISTINCT
        us.user_id,
        g.id,
        'APPLICATION'::entity_manager_enum
      FROM user_submits us
      INNER JOIN submit_nodes sn
        ON sn.id = us.submit_node_id
      INNER JOIN (
        VALUES {mapping_sql}
      ) AS mapping(node_name, group_name)
        ON sn.name = mapping.node_name
      INNER JOIN groups g
        ON g.name = mapping.group_name
      ON CONFLICT ON CONSTRAINT user_groups_distinct DO NOTHING
    """),
    mapping_params,
  )


def downgrade() -> None:
  bind = op.get_bind()

  group_names = [group["group_name"] for group in GROUPS_DATA]

  bind.execute(
    sa.text("""
      DELETE FROM user_groups
      WHERE group_id IN (
        SELECT id
        FROM groups
        WHERE name = ANY(CAST(:group_names AS text[]))
          AND type = 'SUBMIT_NODE'::group_type_enum
      )
    """),
    {
      "group_names": group_names,
    },
  )

  bind.execute(
    sa.text("""
      DELETE FROM groups
      WHERE name = ANY(CAST(:group_names AS text[]))
        AND type = 'SUBMIT_NODE'::group_type_enum
    """),
    {
      "group_names": group_names,
    },
  )

  op.drop_column("groups", "type")
  op.drop_column("groups", "description")
  group_type_enum.drop(bind, checkfirst=True)