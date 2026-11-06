"""The data mapping of c5e1a7d39f20, run against a scratch database built at the previous revision.

test_migration_user_management checks the schema the migration leaves behind. This one seeds the
old tables (user_projects, user_groups, projects.pi) at b2f6d8e4a9c1 in a scratch database,
upgrades to head and checks what the rows became, then downgrades and checks what comes back.
It needs CREATEDB on the test database's role (CI's postgres superuser has it) and skips otherwise.
"""
import asyncio
import os
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from userapp.api.tests.conftest import _seed_db_url

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRATCH_DB = "userapp_migration_scratch"
OLD_REVISION = "b2f6d8e4a9c1"
NEW_REVISION = "c5e1a7d39f20"

BOB_JOINED = datetime(2020, 1, 2, 3, 4, 5)


def _url(database: str | None = None) -> str:
    url = make_url(_seed_db_url()).set(drivername="postgresql+asyncpg")
    if database is not None:
        url = url.set(database=database)
    return url.render_as_string(hide_password=False)


async def _with_engine(url: str, fn, **engine_kwargs):
    engine = create_async_engine(url, connect_args={"ssl": False}, **engine_kwargs)
    try:
        async with engine.connect() as conn:
            return await fn(conn)
    finally:
        await engine.dispose()


def _sql(sql: str, **params) -> list[dict]:
    """One statement against the scratch database, committed"""

    async def run(conn):
        result = await conn.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result] if result.returns_rows else []
        await conn.commit()
        return rows

    return asyncio.run(_with_engine(_url(SCRATCH_DB), run))


def _admin_sql(sql: str) -> None:
    """CREATE / DROP DATABASE cannot run inside a transaction"""

    async def run(conn):
        await conn.execute(text(sql))

    asyncio.run(_with_engine(_url(), run, isolation_level="AUTOCOMMIT"))


def _alembic(direction: str, revision: str) -> None:
    """Run alembic against the scratch database. env.py reads DB_URL, which conftest also honours,
    so it is only set for the duration of the command."""

    config = Config(str(REPO_ROOT / "alembic.ini"))
    previous = os.environ.get("DB_URL")
    os.environ["DB_URL"] = _url(SCRATCH_DB)
    try:
        getattr(command, direction)(config, revision)
    finally:
        if previous is None:
            del os.environ["DB_URL"]
        else:
            os.environ["DB_URL"] = previous


def _seed_old_schema() -> dict:
    """Rows in the shape of b2f6d8e4a9c1, chosen to exercise every branch of the data migration"""

    def user(name: str) -> int:
        return _sql("INSERT INTO users (name, username, active) VALUES (:n, :n, true) RETURNING id", n=name)[0]["id"]

    def project(name: str, pi: int | None) -> int:
        return _sql(
            "INSERT INTO projects (name, accounting_group, pi) VALUES (:n, 'scratch', :pi) RETURNING id", n=name, pi=pi,
        )[0]["id"]

    def group(name: str) -> int:
        return _sql("INSERT INTO groups (name, has_groupdir) VALUES (:n, true) RETURNING id", n=name)[0]["id"]

    def user_project(project_id: int, user_id: int, role: str | None, is_primary: bool, managed_by: str, created_at=None):
        _sql(
            "INSERT INTO user_projects (project_id, user_id, role, is_primary, managed_by, created_at, updated_at) "
            "VALUES (:p, :u, CAST(:r AS role_enum), :pr, CAST(:m AS entity_manager_enum), "
            "COALESCE(CAST(:c AS timestamp), localtimestamp), COALESCE(CAST(:c AS timestamp), localtimestamp))",
            p=project_id, u=user_id, r=role, pr=is_primary, m=managed_by, c=created_at,
        )

    def user_group(group_id: int, user_id: int, managed_by: str):
        _sql(
            "INSERT INTO user_groups (group_id, user_id, managed_by) VALUES (:g, :u, CAST(:m AS entity_manager_enum))",
            g=group_id, u=user_id, m=managed_by,
        )

    u = {name: user(name) for name in ("alice", "bob", "carol", "dave", "erin", "frank", "grace")}

    # Slug collisions, a name longer than the group name limit, and a name with no usable characters
    p = {
        "p1": project("Genome Lab!!", u["alice"]),
        "p2": project("genome_lab", None),
        "p3": project("a" * 40, u["erin"]),      # erin is the pi without a user_projects row
        "p4": project("???", None),
    }
    g = {name: group(name) for name in ("g_one", "g_two", "g_three", "project")}  # "project" collides with p4

    # p1: two MANIFEST rows against two APPLICATION ones
    user_project(p["p1"], u["alice"], "PI", False, "APPLICATION")
    user_project(p["p1"], u["bob"], "MEMBER", True, "MANIFEST", BOB_JOINED)
    user_project(p["p1"], u["carol"], "MEMBER", False, "APPLICATION")
    user_project(p["p1"], u["grace"], "MEMBER", False, "MANIFEST")
    # p2: MORGRIDGE_AD outnumbers MANIFEST
    user_project(p["p2"], u["dave"], "PI", False, "MORGRIDGE_AD")
    user_project(p["p2"], u["erin"], "MEMBER", False, "MORGRIDGE_AD")
    user_project(p["p2"], u["bob"], "MEMBER", False, "MANIFEST")
    user_project(p["p2"], u["carol"], "MEMBER", True, "APPLICATION")
    # p3: application only
    user_project(p["p3"], u["frank"], None, True, "APPLICATION")

    user_group(g["g_one"], u["erin"], "MANIFEST")
    user_group(g["g_one"], u["frank"], "APPLICATION")
    user_group(g["g_two"], u["frank"], "MORGRIDGE_AD")
    user_group(g["g_two"], u["erin"], "MANIFEST")
    user_group(g["g_two"], u["alice"], "MANIFEST")
    user_group(g["g_three"], u["alice"], "APPLICATION")

    node_id = _sql("INSERT INTO submit_nodes (name, group_id) VALUES ('scratch-node', :g) RETURNING id", g=g["g_one"])[0]["id"]

    # Earlier revisions seed groups of their own, so counts are relative to this
    group_count = _sql("SELECT count(*) AS n FROM groups")[0]["n"]
    return {"users": u, "projects": p, "groups": g, "node": node_id, "group_count": group_count}


@pytest.fixture(scope="module")
def upgraded() -> dict:
    try:
        _admin_sql(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)")
        _admin_sql(f"CREATE DATABASE {SCRATCH_DB}")
    except DBAPIError as error:
        pytest.skip(f"Cannot create a scratch database: {error}")
    try:
        _alembic("upgrade", OLD_REVISION)
        seeded = _seed_old_schema()
        _alembic("upgrade", "head")
        yield seeded
    finally:
        _admin_sql(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)")


@pytest.fixture(scope="module")
def downgraded(upgraded) -> dict:
    _alembic("downgrade", OLD_REVISION)
    return upgraded


def _project_groups(project_id: int) -> dict:
    """The three groups of a project after the upgrade: pi, managers (the project group's owner), project"""

    [row] = _sql("SELECT pi_group_id, project_group_id FROM projects WHERE id = :p", p=project_id)
    [pi] = _sql("SELECT * FROM groups WHERE id = :g", g=row["pi_group_id"])
    [project_group] = _sql("SELECT * FROM groups WHERE id = :g", g=row["project_group_id"])
    [managers] = _sql("SELECT * FROM groups WHERE id = :g", g=project_group["owner_group_id"])
    return {"pi": pi, "managers": managers, "project": project_group}


def _direct_users(group_id: int) -> dict[int, dict]:
    rows = _sql("SELECT * FROM group_members WHERE group_id = :g AND member_user_id IS NOT NULL", g=group_id)
    return {r["member_user_id"]: r for r in rows}


def _direct_groups(group_id: int) -> set[int]:
    return {r["member_group_id"] for r in _sql(
        "SELECT member_group_id FROM group_members WHERE group_id = :g AND member_group_id IS NOT NULL", g=group_id,
    )}


def _managed_by(group_id: int) -> str:
    return _sql("SELECT managed_by::text AS m FROM groups WHERE id = :g", g=group_id)[0]["m"]


class TestUpgrade:

    def test_project_groups_are_created_named_and_wired(self, upgraded):
        p = upgraded["projects"]
        first, second, long, odd = (_project_groups(p[k]) for k in ("p1", "p2", "p3", "p4"))

        assert (first["pi"]["name"], first["managers"]["name"], first["project"]["name"]) == \
               ("genome_lab_pi", "genome_lab_managers", "genome_lab")
        # The second project with the same slug gets numbered names
        assert (second["pi"]["name"], second["managers"]["name"], second["project"]["name"]) == \
               ("genome_lab_pi_2", "genome_lab_managers_2", "genome_lab_2")
        # A long name is cut so that the suffix fits
        assert (long["pi"]["name"], long["managers"]["name"], long["project"]["name"]) == \
               ("a" * 29 + "_pi", "a" * 23 + "_managers", "a" * 32)
        # No usable characters falls back to "project", and the existing group of that name is respected
        assert (odd["pi"]["name"], odd["managers"]["name"], odd["project"]["name"]) == \
               ("project_pi", "project_managers", "project_2")

        for groups in (first, second, long, odd):
            assert groups["pi"]["owner_group_id"] is None
            assert groups["managers"]["owner_group_id"] == groups["pi"]["id"]
            assert groups["project"]["owner_group_id"] == groups["managers"]["id"]
            assert _direct_groups(groups["managers"]["id"]) == {groups["pi"]["id"]}
            assert _direct_groups(groups["project"]["id"]) == {groups["pi"]["id"]}
            # Generated groups are not unix groups: the gid trigger was dropped before they were inserted
            assert all(groups[k]["unix_gid"] is None for k in ("pi", "managers", "project"))
            assert all(groups[k]["deleted_at"] is None for k in ("pi", "managers", "project"))

        # Groups that existed keep their trigger-assigned gid
        assert _sql("SELECT unix_gid FROM groups WHERE id = :g", g=upgraded["groups"]["g_one"])[0]["unix_gid"] is not None

    def test_project_memberships(self, upgraded):
        u, p = upgraded["users"], upgraded["projects"]
        first, second, long, odd = (_project_groups(p[k]) for k in ("p1", "p2", "p3", "p4"))

        # PIs come from role = PI and from projects.pi, once each
        assert set(_direct_users(first["pi"]["id"])) == {u["alice"]}
        assert set(_direct_users(second["pi"]["id"])) == {u["dave"]}
        assert set(_direct_users(long["pi"]["id"])) == {u["erin"]}
        assert _direct_users(odd["pi"]["id"]) == {}

        # Every user_projects row becomes a direct member of the project group, PIs included
        assert set(_direct_users(first["project"]["id"])) == {u["alice"], u["bob"], u["carol"], u["grace"]}
        assert set(_direct_users(second["project"]["id"])) == {u["dave"], u["erin"], u["bob"], u["carol"]}
        assert set(_direct_users(long["project"]["id"])) == {u["frank"]}
        assert _direct_users(odd["project"]["id"]) == {}
        assert _direct_users(first["project"]["id"])[u["bob"]]["created_at"] == BOB_JOINED, "created_at survives"

        # Managers groups hold no users of their own
        for groups in (first, second, long, odd):
            assert _direct_users(groups["managers"]["id"]) == {}

    def test_managed_by_moves_to_the_group(self, upgraded):
        p, g = upgraded["projects"], upgraded["groups"]
        first, second, long, odd = (_project_groups(p[k]) for k in ("p1", "p2", "p3", "p4"))

        assert _managed_by(first["project"]["id"]) == "MANIFEST"
        assert _managed_by(second["project"]["id"]) == "MORGRIDGE_AD", "the most common external manager wins"
        assert _managed_by(long["project"]["id"]) == "APPLICATION"
        assert _managed_by(odd["project"]["id"]) == "APPLICATION"
        for groups in (first, second, long, odd):
            assert _managed_by(groups["pi"]["id"]) == "APPLICATION"
            assert _managed_by(groups["managers"]["id"]) == "APPLICATION"

        assert _managed_by(g["g_one"]) == "MANIFEST", "one external row is enough"
        assert _managed_by(g["g_two"]) == "MANIFEST", "two MANIFEST rows beat one MORGRIDGE_AD row"
        assert _managed_by(g["g_three"]) == "APPLICATION"
        assert _managed_by(g["project"]) == "APPLICATION"

    def test_group_memberships(self, upgraded):
        u, g = upgraded["users"], upgraded["groups"]
        assert set(_direct_users(g["g_one"])) == {u["erin"], u["frank"]}
        assert set(_direct_users(g["g_two"])) == {u["frank"], u["erin"], u["alice"]}
        assert set(_direct_users(g["g_three"])) == {u["alice"]}
        assert _direct_users(g["project"]) == {}

    def test_primary_projects(self, upgraded):
        u, p = upgraded["users"], upgraded["projects"]
        primary = {r["id"]: r["primary_project_id"] for r in _sql("SELECT id, primary_project_id FROM users")}
        assert primary[u["bob"]] == p["p1"]
        assert primary[u["carol"]] == p["p2"]
        assert primary[u["frank"]] == p["p3"]
        assert all(primary[u[name]] is None for name in ("alice", "dave", "erin", "grace"))

    def test_effective_membership_and_views(self, upgraded):
        u, p = upgraded["users"], upgraded["projects"]
        first = _project_groups(p["p1"])
        pg, pi, managers = first["project"]["id"], first["pi"]["id"], first["managers"]["id"]

        effective = _sql("SELECT user_id, path FROM group_effective_members WHERE group_id = :g ORDER BY user_id, path", g=pg)
        assert {(r["user_id"], tuple(r["path"])) for r in effective} == {
            (u["alice"], (pg,)), (u["alice"], (pg, pi)),
            (u["bob"], (pg,)), (u["carol"], (pg,)), (u["grace"], (pg,)),
        }
        assert {(r["user_id"], tuple(r["path"])) for r in _sql(
            "SELECT user_id, path FROM group_effective_members WHERE group_id = :g", g=managers,
        )} == {(u["alice"], (managers, pi))}

        joined = {r["id"]: r for r in _sql("SELECT * FROM joined_projects WHERE project_id = :p", p=p["p1"])}
        assert set(joined) == {u["alice"], u["bob"], u["carol"], u["grace"]}
        assert joined[u["alice"]]["is_pi"] is True and joined[u["alice"]]["direct"] is True
        assert joined[u["bob"]]["is_primary"] is True and joined[u["bob"]]["is_pi"] is False
        assert joined[u["bob"]]["created_at"] == BOB_JOINED

        assert {r["user_id"] for r in _sql("SELECT user_id FROM pi_projects WHERE project_id = :p", p=p["p1"])} == {u["alice"]}
        assert {r["user_id"] for r in _sql("SELECT user_id FROM pi_projects WHERE project_id = :p", p=p["p3"])} == {u["erin"]}
        assert {r["user_id"] for r in _sql("SELECT user_id FROM user_submit_nodes WHERE id = :n", n=upgraded["node"])} == \
               {u["erin"], u["frank"]}

        [row] = _sql("SELECT * FROM group_members_view WHERE group_id = :g", g=managers)
        assert row["user_id"] == u["alice"] and row["direct"] is False
        assert row["paths"] == [[managers, pi]] and row["path_names"] == [[first["managers"]["name"], first["pi"]["name"]]]

    def test_generated_groups_are_audited_by_the_system(self, upgraded):
        rows = _sql("SELECT action::text AS action, actor_id, group_id, details FROM audit_log ORDER BY id")
        assert len(rows) == 12 and all(r["action"] == "group_created" and r["actor_id"] is None for r in rows)
        assert all(r["details"]["migration"] == NEW_REVISION for r in rows)

        first = _project_groups(upgraded["projects"]["p1"])
        by_group = {r["group_id"]: r["details"] for r in rows}
        assert by_group[first["pi"]["id"]]["created_for"] == {"entity": "project", "entity_id": upgraded["projects"]["p1"], "role": "pi"}
        assert by_group[first["project"]["id"]]["owner_group_id"] == first["managers"]["id"]

    def test_old_structures_are_gone(self, upgraded):
        tables = {r["table_name"] for r in _sql("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
        assert not {"user_projects", "user_groups", "group_users", "user_group_memberships"} & tables
        columns = {r["column_name"] for r in _sql("SELECT column_name FROM information_schema.columns WHERE table_name = 'projects'")}
        assert "pi" not in columns
        columns = {r["column_name"] for r in _sql("SELECT column_name FROM information_schema.columns WHERE table_name = 'groups'")}
        assert not {"point_of_contact", "has_groupdir"} & columns


class TestDowngrade:

    def test_user_projects_come_back(self, downgraded):
        u, p = downgraded["users"], downgraded["projects"]
        rows = _sql("SELECT project_id, user_id, role::text AS role, is_primary, managed_by::text AS managed_by, created_at FROM user_projects")
        by_key = {(r["project_id"], r["user_id"]): r for r in rows}

        assert {k for k in by_key if k[0] == p["p1"]} == {(p["p1"], u[n]) for n in ("alice", "bob", "carol", "grace")}
        assert by_key[(p["p1"], u["alice"])]["role"] == "PI"
        assert by_key[(p["p1"], u["bob"])]["role"] == "MEMBER" and by_key[(p["p1"], u["bob"])]["is_primary"] is True
        assert by_key[(p["p1"], u["bob"])]["created_at"] == BOB_JOINED
        assert by_key[(p["p1"], u["carol"])]["is_primary"] is False
        # managed_by was per group on the way back, so every row of the project carries the group's
        assert {by_key[(p["p1"], u[n])]["managed_by"] for n in ("alice", "bob", "carol", "grace")} == {"MANIFEST"}

        assert by_key[(p["p2"], u["dave"])]["role"] == "PI"
        assert by_key[(p["p2"], u["carol"])]["is_primary"] is True
        assert {by_key[k]["managed_by"] for k in by_key if k[0] == p["p2"]} == {"MORGRIDGE_AD"}

        # erin was only in p3's pi group, so the pi group adds the row
        assert by_key[(p["p3"], u["erin"])]["role"] == "PI" and by_key[(p["p3"], u["erin"])]["managed_by"] == "APPLICATION"
        assert by_key[(p["p3"], u["frank"])]["role"] == "MEMBER" and by_key[(p["p3"], u["frank"])]["is_primary"] is True
        assert not [k for k in by_key if k[0] == p["p4"]]

        pi = {r["id"]: r["pi"] for r in _sql("SELECT id, pi FROM projects")}
        assert (pi[p["p1"]], pi[p["p2"]], pi[p["p3"]], pi[p["p4"]]) == (u["alice"], u["dave"], u["erin"], None)

    def test_user_groups_come_back_without_the_project_groups(self, downgraded):
        u, g = downgraded["users"], downgraded["groups"]
        rows = _sql("SELECT group_id, user_id, managed_by::text AS managed_by FROM user_groups")
        by_group: dict[int, dict[int, str]] = {}
        for r in rows:
            by_group.setdefault(r["group_id"], {})[r["user_id"]] = r["managed_by"]

        assert set(by_group) == {g["g_one"], g["g_two"], g["g_three"]}, "project groups are user_projects, not user_groups"
        assert by_group[g["g_one"]] == {u["erin"]: "MANIFEST", u["frank"]: "MANIFEST"}
        assert by_group[g["g_two"]] == {u["frank"]: "MANIFEST", u["erin"]: "MANIFEST", u["alice"]: "MANIFEST"}
        assert by_group[g["g_three"]] == {u["alice"]: "APPLICATION"}

    def test_schema_is_back_and_generated_groups_remain(self, downgraded):
        tables = {r["table_name"] for r in _sql("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
        assert {"user_projects", "user_groups"} <= tables
        assert not {"group_members", "group_effective_members", "audit_log"} & tables
        views = {r["table_name"] for r in _sql("SELECT table_name FROM information_schema.views WHERE table_schema = 'public'")}
        assert {"joined_projects", "pi_projects", "group_users", "user_group_memberships", "user_submit_nodes"} <= views

        columns = {r["column_name"] for r in _sql("SELECT column_name FROM information_schema.columns WHERE table_name = 'groups'")}
        assert {"point_of_contact", "has_groupdir"} <= columns
        assert not {"owner_group_id", "managed_by", "deleted_at"} & columns
        assert _sql("SELECT count(*) AS n FROM groups")[0]["n"] == downgraded["group_count"] + 12, "generated groups are left in place"
        generated = ["genome_lab_pi", "genome_lab_managers", "genome_lab", "genome_lab_pi_2", "genome_lab_managers_2",
                     "genome_lab_2", "a" * 29 + "_pi", "a" * 23 + "_managers", "a" * 32, "project_pi", "project_managers", "project_2"]
        assert _sql("SELECT count(*) AS n FROM groups WHERE has_groupdir AND name = ANY(:names)", names=generated)[0]["n"] == 12

        triggers = {r["tgname"] for r in _sql("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")}
        assert {"trg_assign_lowest_unix_gid", "trg_demote_other_primary_projects"} <= triggers
