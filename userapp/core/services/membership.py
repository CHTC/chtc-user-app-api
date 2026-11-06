"""Group membership, ownership and lifecycle.

Every writer of group_members, groups.owner_group_id or group deletion goes through here so that
the cycle checks run under one lock and group_effective_members is rewritten in the same
transaction as the change. Routes never touch those tables directly.
"""
import re
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from userapp.core.models.enum import AuditActionEnum, EntityManagerEnum
from userapp.core.models.tables import Group, GroupMember, GroupEffectiveMember, User, SubmitNode, Project
from userapp.core.services import audit

# Taken by every membership/ownership writer (pg_advisory_xact_lock), so the cycle checks and
# the recompute below never interleave with another writer's.
EFFECTIVE_MEMBERSHIP_LOCK_KEY = 0x55534552

GROUP_NAME_MAX = 32

# One row per distinct path from a group down to a user. The path guard stops a cycle that
# slipped in (for example through a manual edit) from recursing forever; deleted groups are not
# roots, and have no memberships left to traverse.
RECOMPUTE_DELETE_SQL = "DELETE FROM group_effective_members"
RECOMPUTE_INSERT_SQL = """
    WITH RECURSIVE r(root_id, group_id, path) AS (
        SELECT g.id, g.id, ARRAY[g.id]
        FROM groups g
        WHERE g.deleted_at IS NULL
        UNION ALL
        SELECT r.root_id, gm.member_group_id, r.path || gm.member_group_id
        FROM r
        JOIN group_members gm ON gm.group_id = r.group_id
        WHERE gm.member_group_id IS NOT NULL
          AND NOT gm.member_group_id = ANY(r.path)
    )
    INSERT INTO group_effective_members (group_id, user_id, path)
    SELECT r.root_id, gm.member_user_id, r.path
    FROM r
    JOIN group_members gm ON gm.group_id = r.group_id
    WHERE gm.member_user_id IS NOT NULL
"""

# Groups reachable from :gid by following member_group edges downwards
_DESCENDANTS_SQL = """
    WITH RECURSIVE d(id, path) AS (
        SELECT gm.member_group_id, ARRAY[gm.member_group_id]
        FROM group_members gm
        WHERE gm.group_id = :gid AND gm.member_group_id IS NOT NULL
        UNION ALL
        SELECT gm.member_group_id, d.path || gm.member_group_id
        FROM d
        JOIN group_members gm ON gm.group_id = d.id
        WHERE gm.member_group_id IS NOT NULL
          AND NOT gm.member_group_id = ANY(d.path)
    )
    SELECT DISTINCT id FROM d WHERE id <> :gid
"""

# Groups that contain :gid, directly or transitively
_ANCESTORS_SQL = """
    WITH RECURSIVE a(id, path) AS (
        SELECT gm.group_id, ARRAY[gm.group_id]
        FROM group_members gm
        WHERE gm.member_group_id = :gid
        UNION ALL
        SELECT gm.group_id, a.path || gm.group_id
        FROM a
        JOIN group_members gm ON gm.member_group_id = a.id
        WHERE NOT gm.group_id = ANY(a.path)
    )
    SELECT DISTINCT id FROM a WHERE id <> :gid
"""


# Every path from an ancestor down to :gid, as [ancestor, ..., :gid]
_MEMBER_OF_PATHS_SQL = """
    WITH RECURSIVE a(id, path) AS (
        SELECT gm.group_id, ARRAY[gm.group_id, gm.member_group_id]
        FROM group_members gm
        WHERE gm.member_group_id = :gid
        UNION ALL
        SELECT gm.group_id, gm.group_id || a.path
        FROM a
        JOIN group_members gm ON gm.member_group_id = a.id
        WHERE NOT gm.group_id = ANY(a.path)
    )
    SELECT id, path FROM a ORDER BY id, cardinality(path), path
"""


async def lock_membership(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": EFFECTIVE_MEMBERSHIP_LOCK_KEY})


async def recompute_effective_membership(session: AsyncSession) -> None:
    """Rewrite group_effective_members from group_members. Callers hold the lock."""

    # Pending ORM changes have to be visible to the raw SQL below
    await session.flush()
    await session.execute(text(RECOMPUTE_DELETE_SQL))
    await session.execute(text(RECOMPUTE_INSERT_SQL))


async def descendant_group_ids(session: AsyncSession, group_id: int) -> set[int]:
    result = await session.execute(text(_DESCENDANTS_SQL), {"gid": group_id})
    return set(result.scalars())


async def ancestor_group_ids(session: AsyncSession, group_id: int) -> set[int]:
    result = await session.execute(text(_ANCESTORS_SQL), {"gid": group_id})
    return set(result.scalars())


async def member_of_paths(session: AsyncSession, group_id: int) -> dict[int, list[list[int]]]:
    """Groups that contain group_id mapped to every path through which they do, shortest first,
    each from the containing group down to group_id (the same orientation as effective paths)"""

    result = await session.execute(text(_MEMBER_OF_PATHS_SQL), {"gid": group_id})
    paths: dict[int, list[list[int]]] = {}
    for ancestor_id, path in result.all():
        paths.setdefault(ancestor_id, []).append(list(path))
    return paths


async def owner_chain(session: AsyncSession, group_id: int) -> list[int]:
    """[owner, owner's owner, ...], stopping at NULL or when an id repeats"""

    chain: list[int] = []
    seen = {group_id}
    current = group_id
    while True:
        owner_id = await session.scalar(select(Group.owner_group_id).where(Group.id == current))
        if owner_id is None or owner_id in seen:
            return chain
        chain.append(owner_id)
        seen.add(owner_id)
        current = owner_id


async def get_live_group(session: AsyncSession, group_id: int, label: str = "Group") -> Group:
    group = await session.scalar(select(Group).where(Group.id == group_id, Group.deleted_at.is_(None)))
    if group is None:
        raise HTTPException(status_code=404, detail=f"{label} {group_id} not found")
    return group


async def add_member(
    session: AsyncSession,
    *,
    group_id: int,
    actor_id: int | None,
    user_id: int | None = None,
    member_group_id: int | None = None,
    caused_by: int | None = None,
) -> GroupMember:
    if (user_id is None) == (member_group_id is None):
        raise HTTPException(status_code=400, detail="Exactly one of user_id or group_id is required")

    await lock_membership(session)

    await get_live_group(session, group_id)
    if user_id is not None:
        if await session.scalar(select(User.id).where(User.id == user_id)) is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        existing = await session.scalar(
            select(GroupMember.id).where(GroupMember.group_id == group_id, GroupMember.member_user_id == user_id)
        )
    else:
        if member_group_id == group_id:
            raise HTTPException(status_code=400, detail="A group cannot be a member of itself")
        await get_live_group(session, member_group_id, label="Member group")
        # Adding G to H closes a loop exactly when H is already somewhere below G
        if group_id in await descendant_group_ids(session, member_group_id):
            raise HTTPException(status_code=400, detail="Adding this group would create a membership cycle")
        existing = await session.scalar(
            select(GroupMember.id).where(GroupMember.group_id == group_id, GroupMember.member_group_id == member_group_id)
        )

    if existing is not None:
        raise HTTPException(status_code=409, detail="Already a direct member of this group")

    member = GroupMember(
        group_id=group_id,
        member_user_id=user_id,
        member_group_id=member_group_id,
    )
    session.add(member)
    await session.flush()

    await audit.log(
        session,
        action=AuditActionEnum.member_added,
        actor_id=actor_id,
        group_id=group_id,
        member_user_id=user_id,
        member_group_id=member_group_id,
        caused_by=caused_by,
    )
    await recompute_effective_membership(session)

    # Loads member_user / member_group so the row can be returned as GroupMemberGet
    await session.refresh(member)
    return member


async def remove_member(
    session: AsyncSession,
    *,
    group_id: int,
    actor_id: int | None,
    user_id: int | None = None,
    member_group_id: int | None = None,
    caused_by: int | None = None,
) -> None:
    """Deletes one direct membership row. Effective membership gained through other paths stays."""

    if (user_id is None) == (member_group_id is None):
        raise HTTPException(status_code=400, detail="Exactly one of user_id or group_id is required")

    await lock_membership(session)

    stmt = select(GroupMember).where(GroupMember.group_id == group_id)
    if user_id is not None:
        stmt = stmt.where(GroupMember.member_user_id == user_id)
    else:
        stmt = stmt.where(GroupMember.member_group_id == member_group_id)
    member = await session.scalar(stmt)
    if member is None:
        raise HTTPException(status_code=404, detail="Not a direct member of this group")

    await session.delete(member)
    await session.flush()

    await audit.log(
        session,
        action=AuditActionEnum.member_removed,
        actor_id=actor_id,
        group_id=group_id,
        member_user_id=user_id,
        member_group_id=member_group_id,
        caused_by=caused_by,
    )
    await recompute_effective_membership(session)


async def set_owner_group(
    session: AsyncSession,
    *,
    group_id: int,
    owner_group_id: int | None,
    actor_id: int | None,
) -> Group:
    """Only staff call this. Ownership is not part of effective membership, so no recompute."""

    await lock_membership(session)

    group = await get_live_group(session, group_id)

    if owner_group_id is not None:
        if owner_group_id == group_id:
            raise HTTPException(status_code=400, detail="A group cannot own itself")
        await get_live_group(session, owner_group_id, label="Owner group")
        # If this group already sits somewhere above the new owner, the new owner would end up
        # owning the group that owns it
        if group_id in await owner_chain(session, owner_group_id):
            raise HTTPException(status_code=400, detail="Setting this owner group would create an ownership loop")

    old_owner_id = group.owner_group_id
    if old_owner_id == owner_group_id:
        return group

    group.owner_group_id = owner_group_id
    await session.flush()

    await audit.log(
        session,
        action=AuditActionEnum.owner_group_changed,
        actor_id=actor_id,
        group_id=group_id,
        member_group_id=owner_group_id,
        details={"old": old_owner_id, "new": owner_group_id},
    )
    await session.refresh(group)
    return group


def slugify_group_name(text: str) -> str:
    slug = re.sub(r'[^a-z0-9_-]', '_', text.lower())
    slug = re.sub(r'_+', '_', slug)
    return slug.strip('_-')


async def unique_group_name(session: AsyncSession, base: str, suffix: str = "") -> str:
    """base + suffix cut to 32 characters by truncating base, then _2, _3, ... while taken.
    Deleted groups keep their names, so they count as taken."""

    async def taken(name: str) -> bool:
        return await session.scalar(select(Group.id).where(Group.name == name)) is not None

    candidate = base[:GROUP_NAME_MAX - len(suffix)] + suffix
    n = 2
    while await taken(candidate):
        number = f"_{n}"
        candidate = base[:GROUP_NAME_MAX - len(suffix) - len(number)] + suffix + number
        n += 1
    return candidate


async def _insert_group(
    session: AsyncSession,
    *,
    name: str,
    owner_group_id: int | None,
    unix_gid: int | None = None,
    description: str | None = None,
    managed_by: EntityManagerEnum = EntityManagerEnum.APPLICATION,
) -> Group:
    group = Group(
        name=name,
        owner_group_id=owner_group_id,
        unix_gid=unix_gid,
        description=description,
        managed_by=managed_by,
    )
    session.add(group)
    await session.flush()
    return group


async def create_group(
    session: AsyncSession,
    *,
    actor_id: int | None,
    name: str,
    unix_gid: int | None = None,
    description: str | None = None,
    managed_by: EntityManagerEnum = EntityManagerEnum.APPLICATION,
    owner_group_id: int | None = None,
    administration: Literal["none", "owners", "owners_and_managers"] = "none",
    created_for: dict | None = None,
) -> Group:
    """Creates a group, and with administration != "none" the administrator groups that own it:

        owners:               O (owned by staff) owns B
        owners_and_managers:  O (owned by staff) owns M, O is a member of M, M owns B
    """

    if administration not in ("none", "owners", "owners_and_managers"):
        raise HTTPException(status_code=400, detail=f"Unknown administration {administration!r}")
    if administration != "none" and owner_group_id is not None:
        raise HTTPException(status_code=400, detail="owner_group_id cannot be combined with administration")

    await lock_membership(session)

    if owner_group_id is not None:
        await get_live_group(session, owner_group_id, label="Owner group")

    owners_group = managers_group = None
    if administration != "none":
        owners_group = await _insert_group(
            session, name=await unique_group_name(session, name, "_owners"), owner_group_id=None,
        )
        if administration == "owners_and_managers":
            managers_group = await _insert_group(
                session, name=await unique_group_name(session, name, "_managers"), owner_group_id=owners_group.id,
            )
        owner_group_id = (managers_group or owners_group).id

    group = await _insert_group(
        session, name=name, owner_group_id=owner_group_id, unix_gid=unix_gid,
        description=description, managed_by=managed_by,
    )

    details = {"name": group.name, "owner_group_id": group.owner_group_id}
    if created_for is not None:
        details["created_for"] = created_for
    created = await audit.log(
        session, action=AuditActionEnum.group_created, actor_id=actor_id, group_id=group.id, details=details,
    )

    # The administrator groups' entries point back at the entry for the group they were made for
    for admin_group, role in ((owners_group, "owners"), (managers_group, "managers")):
        if admin_group is None:
            continue
        await audit.log(
            session,
            action=AuditActionEnum.group_created,
            actor_id=actor_id,
            group_id=admin_group.id,
            caused_by=created.id,
            details={
                "name": admin_group.name,
                "owner_group_id": admin_group.owner_group_id,
                "created_for": {"entity": "group", "entity_id": group.id, "role": role},
            },
        )

    if managers_group is not None:
        # Owners edit the base group as well because they are members of the managers group;
        # owning the managers group alone would not be enough
        await add_member(
            session, group_id=managers_group.id, actor_id=actor_id,
            member_group_id=owners_group.id, caused_by=created.id,
        )

    # created_at / updated_at are server defaults and must be loaded before the route serializes it
    await session.refresh(group)
    return group


async def create_project_groups(
    session: AsyncSession,
    *,
    actor_id: int | None,
    project: Project,
) -> tuple[Group, Group, Group]:
    """Creates (pi_group, managers_group, project_group) for a project and points the project at
    them. pi has no owner and is a member of managers and of the project group; managers owns
    nothing but the project group, and the pi group owns managers (the design's Project section)."""

    await lock_membership(session)

    slug = slugify_group_name(project.name) or "project"

    async def new_group(suffix: str, owner_group_id: int | None, role: str) -> Group:
        group = await _insert_group(
            session, name=await unique_group_name(session, slug, suffix), owner_group_id=owner_group_id,
        )
        await audit.log(
            session,
            action=AuditActionEnum.group_created,
            actor_id=actor_id,
            group_id=group.id,
            details={
                "name": group.name,
                "owner_group_id": owner_group_id,
                "created_for": {"entity": "project", "entity_id": project.id, "role": role},
            },
        )
        return group

    pi_group = await new_group("_pi", None, "pi")
    managers_group = await new_group("_managers", pi_group.id, "managers")
    project_group = await new_group("", managers_group.id, "project")

    await add_member(session, group_id=managers_group.id, actor_id=actor_id, member_group_id=pi_group.id)
    await add_member(session, group_id=project_group.id, actor_id=actor_id, member_group_id=pi_group.id)

    project.pi_group_id = pi_group.id
    project.project_group_id = project_group.id
    await session.flush()

    return pi_group, managers_group, project_group


async def delete_group(session: AsyncSession, *, group_id: int, actor_id: int | None) -> None:
    """Soft delete. The name and unix_gid stay on the row so they are never reused."""

    await lock_membership(session)

    group = await get_live_group(session, group_id)
    # Read before the flush expires the row's attributes
    group_name = group.name
    group.deleted_at = func.now()
    await session.flush()

    deleted = await audit.log(
        session, action=AuditActionEnum.group_deleted, actor_id=actor_id, group_id=group_id,
        details={"name": group_name},
    )

    # Memberships in both directions: the group's own members and its membership in other groups
    memberships = (await session.execute(
        select(GroupMember).where((GroupMember.group_id == group_id) | (GroupMember.member_group_id == group_id))
    )).scalars().all()
    for membership in memberships:
        await audit.log(
            session,
            action=AuditActionEnum.member_removed,
            actor_id=actor_id,
            group_id=membership.group_id,
            member_user_id=membership.member_user_id,
            member_group_id=membership.member_group_id,
            caused_by=deleted.id,
            details={"reason": "group_deleted"},
        )
        await session.delete(membership)
    await session.flush()

    # Groups this one owned become staff-only
    owned = (await session.execute(select(Group).where(Group.owner_group_id == group_id))).scalars().all()
    for owned_group in owned:
        owned_group.owner_group_id = None
        await audit.log(
            session,
            action=AuditActionEnum.owner_group_changed,
            actor_id=actor_id,
            group_id=owned_group.id,
            member_group_id=group_id,
            caused_by=deleted.id,
            details={"old": group_id, "new": None, "reason": "group_deleted"},
        )

    # Access entries that pointed at the group keep existing but grant access to no one
    references = (
        ("submit_node", SubmitNode, SubmitNode.group_id, "group_id"),
        ("project", Project, Project.pi_group_id, "pi_group_id"),
        ("project", Project, Project.project_group_id, "project_group_id"),
    )
    for entity, model, column, field in references:
        rows = (await session.execute(select(model).where(column == group_id))).scalars().all()
        for row in rows:
            setattr(row, field, None)
            await audit.log(
                session,
                action=AuditActionEnum.metadata_changed,
                actor_id=actor_id,
                group_id=group_id,
                caused_by=deleted.id,
                details={
                    "entity": entity,
                    "entity_id": row.id,
                    "changes": {field: {"old": group_id, "new": None}},
                    "reason": "group_deleted",
                },
            )
    await session.flush()

    await recompute_effective_membership(session)


UNIX_GID_LOCK_KEY = 0x55534547  # serializes allocations so two groups never pick the same free gid
UNIX_GID_RANGE = (40000, 60000)

# The rule the old trg_assign_lowest_unix_gid insert trigger used: the lowest gid in range that
# no group holds and no user has as a uid
_NEXT_FREE_GID_SQL = """
    SELECT gid FROM (
        SELECT generate_series(CAST(:low AS integer), CAST(:high AS integer)) AS gid
        EXCEPT SELECT unix_gid FROM groups WHERE unix_gid IS NOT NULL
        EXCEPT SELECT unix_uid FROM users WHERE unix_uid IS NOT NULL
    ) AS available
    ORDER BY gid
    LIMIT 1
"""


async def allocate_unix_gid(session: AsyncSession, *, group_id: int, actor_id: int | None) -> Group:
    """Gives a group without a unix_gid the lowest free one. Staff call this for groups that
    should be unix groups; new groups no longer get one automatically."""

    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": UNIX_GID_LOCK_KEY})

    group = await get_live_group(session, group_id)
    if group.unix_gid is not None:
        raise HTTPException(status_code=409, detail=f"Group already has unix_gid {group.unix_gid}")

    low, high = UNIX_GID_RANGE
    gid = await session.scalar(text(_NEXT_FREE_GID_SQL), {"low": low, "high": high})
    if gid is None:
        raise HTTPException(status_code=409, detail=f"No available unix_gid in range {low}-{high}")

    group.unix_gid = gid
    await session.flush()
    await audit.log(
        session,
        action=AuditActionEnum.metadata_changed,
        actor_id=actor_id,
        group_id=group_id,
        details={"entity": "group", "entity_id": group_id, "changes": {"unix_gid": {"old": None, "new": gid}}, "reason": "allocated"},
    )
    await session.refresh(group)
    return group


async def is_group_administrator(session: AsyncSession, user_id: int, group_id: int) -> bool:
    """The rule for every group: effective member of its owner_group. Staff are checked by callers."""

    owner_group_id = await session.scalar(select(Group.owner_group_id).where(Group.id == group_id))
    if owner_group_id is None:
        return False
    result = await session.scalar(
        text("SELECT 1 FROM group_effective_members WHERE group_id = :g AND user_id = :u LIMIT 1"),
        {"g": owner_group_id, "u": user_id},
    )
    return result is not None


async def administers_any_group(session: AsyncSession, user_id: int) -> bool:
    """Whether the user is an effective member of some live group's owner group: a PI (the pi
    group owns the managers group) or any other group owner. They get to look users and groups
    up so they can add them."""

    found = await session.scalar(
        select(Group.id).where(
            Group.deleted_at.is_(None),
            Group.owner_group_id.in_(
                select(GroupEffectiveMember.group_id).where(GroupEffectiveMember.user_id == user_id)
            ),
        ).limit(1)
    )
    return found is not None


async def administrable_group_ids(session: AsyncSession, user_id: int) -> set[int]:
    result = await session.execute(
        select(Group.id).where(
            Group.owner_group_id.in_(
                select(GroupEffectiveMember.group_id).where(GroupEffectiveMember.user_id == user_id)
            )
        )
    )
    return set(result.scalars())
