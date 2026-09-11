# Wrappers to the HTCondor CLI
# Does not use the HTCondor python package to save locking up the GIL

import asyncio
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

CONDOR_Q = shutil.which("condor_q") or "/usr/bin/condor_q"
_SCHEDD_SEM = asyncio.Semaphore(4)          # protect the schedd, not just yourself

_ENV = {
    "PATH": "/usr/bin:/bin",
    "CONDOR_CONFIG": os.environ.get("CONDOR_CONFIG", "/etc/condor/condor_config"),
    "_CONDOR_Q_QUERY_TIMEOUT": "10",        # best-effort; the real guarantee is the wait_for below
}

# Always requested so every ad has a stable key, regardless of what the caller asked for.
_KEY_ATTRS = ("ClusterId", "ProcId")

# The queue-date attribute the [start, end) window is applied to.
_WINDOW_ATTR = "QDate"


def cq_quote(s: str) -> str:
    """ClassAd string literal. Mirrors classad2.quote()."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def yesterday() -> tuple[datetime, datetime]:
    """Yesterday's calendar day as a [start, end) pair of local midnights."""
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=1), midnight


def window_constraint(start: datetime, end: datetime) -> str:
    """ClassAd expression for QDate in [start, end).

    Naive datetimes are read as local time, which is what the schedd's own
    epoch QDate is relative to. Half-open so adjacent windows neither overlap
    nor drop a job that landed exactly on midnight.
    """
    if end <= start:
        raise ValueError(f"end ({end}) must be after start ({start})")
    return f"{_WINDOW_ATTR} >= {int(start.timestamp())} && {_WINDOW_ATTR} < {int(end.timestamp())}"


class ScheddError(RuntimeError):
    pass


class ScheddTimeout(ScheddError):
    pass


def _intern(value: Any) -> Any:
    """Recursively intern every string in a decoded ClassAd.

    Attribute names and repeated values (Owner, JobStatus expressions, project
    names) collapse onto one object per distinct string, which is most of the
    footprint of a few thousand ads. Note that sys.intern() strings live for the
    life of the process -- if a caller starts pulling high-cardinality
    attributes (Cmd, Args, Iwd), narrow the interning to keys only.
    """
    if isinstance(value, str):
        return sys.intern(value)
    if isinstance(value, dict):
        return {sys.intern(k): _intern(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_intern(v) for v in value]
    return value


def _ad_key(ad: dict, index: int) -> str:
    """"<cluster>.<proc>" if the schedd gave us both, otherwise a positional key."""
    cluster, proc = ad.get("ClusterId"), ad.get("ProcId")
    if cluster is None:
        return sys.intern(f"unknown.{index}")
    return sys.intern(f"{cluster}.{proc if proc is not None else 0}")


async def condor_q(constraint: str | None = None, attrs: list[str] | None = None,
                   start: datetime | None = None, end: datetime | None = None,
                   limit: int = 2000, timeout: float = 15.0,
                   pool: str | None = None, all_users: bool = False,
                   global_: bool = False, name: str | None = None) -> dict[str, dict]:
    """Query a schedd and return {"<cluster>.<proc>": ad} with all strings interned.

    The QDate window is always applied: `start` and `end` each default to the
    corresponding edge of yesterday, and `constraint` is ANDed on top of it
    rather than replacing it. `attrs` are requested on top of the key
    attributes; None asks for the key attributes alone. `all_users` drops the
    default filter to the invoking user's own jobs (-allusers).

    Which schedd answers is set by three options. `pool` only points the query
    at a different collector (-pool) -- on its own the local schedd still
    answers. `global_` fans the query out to every schedd in that pool
    (-global), and `name` targets one named schedd (-name); the two are mutually
    exclusive. Note that -global multiplies both the wall-clock cost and the ad
    count, so `limit` and `timeout` usually need raising alongside it.

    Keys are only unique within one schedd: two schedds can each hold cluster 12
    proc 0. A caller fanning out over several must qualify the keys itself
    (GlobalJobId is the pool-wide identity).

    Raises ValueError if the window is empty or global_ and name are combined,
    ScheddTimeout if condor_q outlives `timeout`, ScheddError on a non-zero exit
    or unparseable output.
    """
    if global_ and name is not None:
        raise ValueError("global_ queries every schedd in the pool; it cannot be combined with name")

    default_start, default_end = yesterday()
    window = window_constraint(
        default_start if start is None else start,
        default_end if end is None else end,
    )
    full_constraint = f"({window}) && ({constraint})" if constraint else window

    requested = list(dict.fromkeys([*_KEY_ATTRS, *(attrs or ())]))
    argv = [CONDOR_Q, "-json"]
    if pool is not None:
        argv += ["-pool", pool]
    if global_:
        argv.append("-global")
    if name is not None:
        argv += ["-name", name]
    if all_users:
        argv.append("-allusers")
    argv += ["-constraint", full_constraint,
             "-attributes", ",".join(requested), "-limit", str(limit)]

    async with _SCHEDD_SEM:
        proc = await asyncio.create_subprocess_exec(
            *argv, env=_ENV,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()                # reap, or you leak the child
            raise ScheddTimeout(f"condor_q exceeded {timeout}s")

    if proc.returncode != 0:
        raise ScheddError(err.decode(errors="replace").strip()[:500])

    out = out.strip()
    if not out:
        logger.info("condor_q returned 0 ads (empty output), interned dict holds 0 entries")
        return {}                            # empty output == zero jobs

    try:
        ads = json.loads(out)
    except json.JSONDecodeError as e:
        raise ScheddError(f"could not parse condor_q output: {e}")

    jobs: dict[str, dict] = {}
    for index, ad in enumerate(ads):
        jobs[_ad_key(ad, index)] = _intern(ad)

    attr_count = sum(len(ad) for ad in jobs.values())
    footprint = sys.getsizeof(jobs) + sum(sys.getsizeof(ad) for ad in jobs.values())
    logger.info(
        "condor_q interned dictionary: %d entries, %d attributes, ~%d bytes of dict overhead "
        "(limit=%d, attrs=%d)",
        len(jobs), attr_count, footprint, limit, len(requested),
    )

    if len(ads) != len(jobs):
        logger.warning("condor_q returned %d ads but only %d unique job keys", len(ads), len(jobs))

    return jobs
