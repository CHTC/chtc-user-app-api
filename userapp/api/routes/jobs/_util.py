"""Everything behind the /jobs history endpoints.

Ported from the two bake scripts that fed the job viewer when its data was static
(build-stacked-bar-data.mjs and build-day-data.mjs). The arithmetic is the same;
what changed is where the numbers come from and who is allowed to see them:

  * The Owner filter is the caller's netid rather than an environment variable.
    An admin may ask for someone else's netid; nobody else can.
  * Anonymization is gone. It existed so a public site could publish one user's
    jobs; here a user is looking at their own, so real ClusterIds and real batch
    names are exactly what they need. That also removes the two label stores.
  * Day boundaries are DST-correct (see the note on bucketing below).

Both halves of the answer come from htcondordb, the ClassAd database each access
point runs alongside its schedd. Only ap2001's is asked for now (HTCONDORDB_*
below); the other APs are not consulted. It holds two tables that matter here:

  history  one terminal record per job (Completed or Removed), append-only and
           zone-mapped on EnteredHistoryTime, so a time-bounded query only
           opens the segments that can hold matches.
  jobs     the live queue, which knows nothing about jobs that already finished.

A cluster in flight appears in both, split across them. The two are read as one
snapshot (see fetch_live_jobs), so each job lands in exactly one of them.

Windows that tile
-----------------
Both per-owner endpoints answer for a window of days, and the viewer now asks for
a long span as a run of short windows -- one per week -- and merges them, so it
can paginate a calendar without re-reading everything on every page. That only
works if each window's answer is complete on its own, which pins down which jobs
a window selects: every job that was open at any point inside it. Placed before
the window closed, and either finished on or after it opened or not finished at
all. A job that outlives the window is in it; a job that finished before it
opened is not.

The day summary used to select by "had a transition inside the window" instead,
which is the same set for a window ending today and a different one for a window
ending in the past: a job placed on the last day of a past window and finished a
week later has no transition inside it, and dropping it hollowed out the
end-of-day census and cut every cohort's story short at the window's edge. See
fetch_day_buckets and _DayAggregator for what changed.

Bucketing and DST
-----------------
The bakes bucketed with a fixed 86400s interval plus an offset, and refused to
run at all when the window straddled a DST transition, because fixed intervals
cannot line up with local midnight on a 23- or 25-hour day. A bake can decline to
run; a live endpoint cannot -- a rolling 35-day window contains the transition
for 35 consecutive days, so that rule would break the page for over a month,
twice a year.

So htcondordb is asked for one-hour buckets (time_bucket, which floors to the
UTC hour), and this module files each hour into the local day and bin that
contain it. That is exact rather than approximate because every boundary the
calendar draws -- local midnights and bin starts -- falls on a UTC hour in a zone
whose offsets are whole hours, as America/Chicago's are; Calendar refuses a zone
where that does not hold. The one residue is that a sub-day bin spanning a DST
transition is an hour short or long; that bin is still assigned to the day it
starts in, which is what the viewer draws.

What it costs
-------------
Measured against ap2001 for its busiest owner, about 410k jobs in a 35-day
window. Grouping by up to three attributes every record carries (ClusterId,
QDate, EnteredCurrentStatus) is answered from the archive's columns in one to two
seconds. Anything that touches an attribute only some records carry --
JobStartDate, JobBatchName, a FILTER predicate -- or a fourth group key, falls to
a per-record path that took 26 to 28 seconds for the same owner. So the queries
are shaped around that line: the status split is two WHERE clauses rather than a
group key, jobs that never started are found by subtraction rather than by
testing JobStartDate, and only the day summary, which cannot do without start
times, pays for the slow path once.
"""

import asyncio
import logging
import os
import re
from array import array
from bisect import bisect_right
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from time import monotonic
from time import time as epoch_now
from typing import Any, Awaitable, Callable, Optional, Sequence
from zoneinfo import ZoneInfo

import htcondordb
from fastapi import HTTPException
from sqlalchemy import select

from userapp.core.models.tables import User
from userapp.core.models.views import UserSubmitView

logger = logging.getLogger(__name__)

# --- Configuration ------------------------------------------------------------

# ap2001's htcondordb. Addressed by hostname rather than by the IP its collector ad
# carries: the daemon's TLS certificate is checked against the host in this
# address, and it names only the hostname. The sock name is fixed on ap2001; on
# other APs it is generated and changes on restart. Authentication is whatever
# CONDOR_CONFIG provides -- an IDTOKEN signed by ap2001 in its token directory.
HTCONDORDB_ADDRESS = os.environ.get(
    "HTCONDORDB_ADDRESS", "<ap2001.chtc.wisc.edu:9618?sock=htcondordb>"
)
# The schedd whose queue and history that database mirrors, for the payload's
# description of where the numbers came from.
HTCONDORDB_SCHEDD = os.environ.get("HTCONDORDB_SCHEDD", "ap2001.chtc.wisc.edu")
HTCONDORDB_TIMEOUT = float(os.environ.get("HTCONDORDB_TIMEOUT", "120"))
HISTORY_TABLE = "history"
JOBS_TABLE = "jobs"

CONDOR_POOL = os.environ.get("CONDOR_POOL", "cm.chtc.wisc.edu")

# Width of the time buckets asked of htcondordb. One hour is the narrowest bin
# the viewer draws, and every local day and bin boundary falls on one (see the
# module note), so hour buckets file exactly into either.
BUCKET = "1h"
BUCKET_SECONDS = 3600

# The zone the calendar is drawn in. Deliberately not the server's own timezone:
# a container running in UTC would otherwise cut every day six hours early for a
# user in Madison.
TIMEZONE = os.environ.get("JOB_HISTORY_TIMEZONE", "America/Chicago")
TZ = ZoneInfo(TIMEZONE)

# Days of history, counting back from today. The default is sized so the viewer's
# longest period (30 complete days) fits inside the window with room to spare.
DEFAULT_DAYS_BACK = 34
MAX_DAYS_BACK = 90

DEFAULT_BIN_HOURS = 4
# Divisors of 24 only: the viewer assumes a whole number of bins per day.
ALLOWED_BIN_HOURS = (1, 2, 3, 4, 6, 8, 12, 24)

DAY_SECONDS = 86400

# How far back to look in history for a job that is also still in the live
# table. The two are synced from the schedd separately, so a job that has just
# left the queue can briefly be in both; an hour is far more lag than either
# sync has.
LIVE_OVERLAP_SECONDS = 3600

# Every attribute either endpoint reads off a live job, in the order they are
# selected. One list rather than one per endpoint, so the two can share a single
# read of the queue.
LIVE_ATTRS = [
    "ClusterId", "ProcId", "QDate", "JobStatus", "JobStartDate", "EnteredCurrentStatus",
    # A cluster still entirely in the queue has no terminal record at all, so
    # this is the only place its batch name can come from.
    "JobBatchName",
]

# These aggregations cost up to half a minute of htcondordb time for a busy
# owner, and a page refresh asks for the identical window, so an answer is
# reused briefly. Set to 0 to disable.
CACHE_SECONDS = float(os.environ.get("JOB_HISTORY_CACHE_SECONDS", "60"))
CACHE_MAX_ENTRIES = 64

# The user table is assembled one day at a time rather than as a single query
# over the whole range. One day of ap2001's history answers in about a second,
# and days tile an arbitrary range exactly, which whole weeks cannot.
#
# The decomposition only holds because every figure in the table is a sum or a
# count, which merge across days exactly. It is the reason there is no median
# runtime and no distinct-cluster count here: percentiles and cardinality cannot
# be added up from partials, and computing them range-wide would cost more than
# the rest of the table put together.
#
# A day that has ended is settled: history may still receive a straggler, but not
# enough to be worth re-reading every minute. Ranges overlap constantly, so a
# cached day is reused by nearly every subsequent range a reader asks for.
DAY_CACHE_SECONDS_PAST = float(os.environ.get("JOB_DAY_CACHE_SECONDS", "21600"))

# A long range would otherwise open one query per day all at once, which costs
# htcondordb more than it costs this process.
DAY_FETCH_CONCURRENCY = int(os.environ.get("JOB_DAY_CONCURRENCY", "12"))

# Longest range that may be asked for. A year of days still answers, but slowly
# enough that it is worth making the caller opt into it a quarter at a time.
MAX_RANGE_DAYS = 366

# JobStatus of a removed job. Every other status in history is counted as
# completed: a job leaves the queue by finishing or by being removed.
REMOVED_STATUS = 3

# Terminal state buckets. Hold is deliberately not one of them: the history
# records carry no NumHolds/LastHoldTime for most jobs, so a hold count would be
# a fabrication. Live jobs in JobStatus 5 (Held) fold into Queued, and that is
# logged when it happens.
STATE_QUEUED = 0
STATE_RUNNING = 1
STATE_COMPLETED = 2
STATE_REMOVED = 3
STATE_COUNT = 4
STATE_NAMES = ["queued", "running", "completed", "removed"]

# Sankey flow slots, per (cluster, day). The diagram has three ranks:
#
#   Placed Today, Placed Before  ->  Active  ->  Completed
#                                            \-> Removed
#
# with the two Placed nodes also able to reach Removed (and, rarely, Completed)
# directly, for jobs that left the queue without ever running.
FLOW_PLACED_TODAY_ACTIVE = 0
FLOW_PLACED_BEFORE_ACTIVE = 1
FLOW_ACTIVE_COMPLETED = 2
FLOW_ACTIVE_REMOVED = 3
FLOW_PLACED_TODAY_REMOVED = 4
FLOW_PLACED_BEFORE_REMOVED = 5
FLOW_PLACED_TODAY_COMPLETED = 6
FLOW_PLACED_BEFORE_COMPLETED = 7
FLOW_COUNT = 8

# Sentinel day key for the census taken at the moment the window opens.
WINDOW_START_DAY = "window-start"

# Stand-in for jobs that carry no JobBatchName. They are a real group, not an
# error, and they get their own bucket so the batch totals still account for
# every job on the page. It has to be a value no real batch name would collide
# with.
NO_BATCH = "__no_batch__"


# --- Calendar -----------------------------------------------------------------


def _midnight(day: date) -> int:
    """Epoch seconds of local midnight starting `day`, DST included."""
    return int(datetime.combine(day, time.min, tzinfo=TZ).timestamp())


class Calendar:
    """The window, its day grid, and its sub-day bin grid, all in local time.

    Boundaries are built from calendar dates rather than by adding 86400 to the
    previous one, so a 23- or 25-hour day is the length it really was. Hour
    buckets and raw timestamps are both resolved against these boundaries by
    binary search.
    """

    def __init__(self, first: date, last: date, bin_hours: int):
        """`first` and `last` are both inclusive, in the calendar's own zone.

        Taking explicit dates rather than a number of days back from today is
        what lets the viewer be pointed at a past window. Anchoring to today was
        fine while this was the only job page, but the table in front of it can
        now ask about any range, and a rolling "last 35 days" would answer a
        question nobody asked: opening a user from a July range would show late
        July through today.
        """
        dates = [first + timedelta(days=i) for i in range((last - first).days + 1)]

        self.days = [d.isoformat() for d in dates]
        self.day_boundaries = [_midnight(d) for d in dates]
        self.start_sec = self.day_boundaries[0]
        self.end_sec = _midnight(last + timedelta(days=1))
        self.start = datetime.combine(first, time.min, tzinfo=TZ)
        self.end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=TZ)

        self.bin_hours = bin_hours
        self.bins_per_day = 24 // bin_hours
        # Non-decreasing rather than strictly increasing: on a spring-forward day
        # a sub-3-hour bin can start at a local time that does not exist, which
        # collapses onto its neighbour. Such a bin simply stays empty, since the
        # search below can never land in it.
        self.bin_boundaries = [
            int(datetime.combine(d, time(hour=k * bin_hours), tzinfo=TZ).timestamp())
            for d in dates
            for k in range(self.bins_per_day)
        ]
        self.total_bins = len(self.bin_boundaries)

        # Hour buckets file into days and bins exactly only if every boundary is
        # on the hour. True of any zone whose offsets are whole hours; refused
        # loudly for one that is not, rather than smearing an hour's jobs across
        # two days.
        misaligned = [
            boundary for boundary in self.bin_boundaries + [self.end_sec]
            if boundary % BUCKET_SECONDS
        ]
        if misaligned:
            raise HTTPException(
                status_code=500,
                detail=f"{TIMEZONE} has boundaries off the hour; job history needs a whole-hour zone",
            )

    def __len__(self) -> int:
        return len(self.days)

    def day_index(self, seconds: Any) -> int:
        """Day index for an epoch-seconds timestamp, or -1 if outside the window."""
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            return -1
        if value < self.start_sec or value >= self.end_sec:
            return -1
        return bisect_right(self.day_boundaries, value) - 1

    def bin_index(self, seconds: Any) -> int:
        """Bin index for an epoch-seconds timestamp, or -1 if outside the window."""
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            return -1
        if value < self.start_sec or value >= self.end_sec:
            return -1
        return bisect_right(self.bin_boundaries, value) - 1

    def day_index_clamped(self, seconds: Any) -> int:
        """Day index, or -1 before the window, or len(self) at or after its end.

        The plain day_index folds both sides into -1, which was fine while a
        window always ended today: nothing could lie beyond it. A window in the
        past has jobs that started or finished after it closed, and those must
        not be mistaken for ones that started or finished before it opened -- the
        first was queued throughout, the second was never there at all.
        """
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            return -1
        if value < self.start_sec:
            return -1
        if value >= self.end_sec:
            return len(self)
        return bisect_right(self.day_boundaries, value) - 1

    def day_key(self, seconds: Any) -> Optional[str]:
        """The local calendar date of a timestamp as "YYYY-MM-DD", inside the
        window or not. None for junk, and for the zero that means "no such
        timestamp"."""
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return datetime.fromtimestamp(value, TZ).date().isoformat()

    def open_inside(self, queued_at: Any, ended_at: Any) -> bool:
        """Whether a terminal job was open at some point inside the window:
        placed before it closed, and finished on or after it opened or placed
        inside it.

        That is the selection that makes windows tile (see the module note). It
        is applied here, to hour buckets, rather than in the query, because an OR
        in the WHERE clause cost htcondordb about three seconds for a busy owner
        and the buckets answer it exactly: the window's edges are on the hour, so
        an hour bucket is on a side of an edge exactly when its jobs are.
        """
        queued = _as_seconds(queued_at)
        ended = _as_seconds(ended_at)
        if queued is None or queued >= self.end_sec:
            return False
        return queued >= self.start_sec or (ended is not None and ended >= self.start_sec)


def _check_bin_hours(bin_hours: int) -> None:
    if bin_hours not in ALLOWED_BIN_HOURS:
        raise HTTPException(
            status_code=422,
            detail=f"bin_hours must be one of {list(ALLOWED_BIN_HOURS)}",
        )


def build_calendar(days_back: int, bin_hours: int = DEFAULT_BIN_HOURS) -> Calendar:
    """A window of `days_back` days ending today, both ends inclusive."""
    if not 0 < days_back <= MAX_DAYS_BACK:
        raise HTTPException(
            status_code=422,
            detail=f"days_back must be between 1 and {MAX_DAYS_BACK}",
        )
    _check_bin_hours(bin_hours)
    today = datetime.now(TZ).date()
    return Calendar(today - timedelta(days=days_back), today, bin_hours)


def build_calendar_for_range(start: str, end: str, bin_hours: int = DEFAULT_BIN_HOURS) -> Calendar:
    """A window given as `YYYY-MM-DD` bounds, with `end` exclusive.

    The exclusive end matches /jobs/users, so the table and the calendar can pass
    one pair of dates between them without either having to adjust it. Calendar
    itself works in inclusive days, which is why `end` loses a day here.
    """
    first, last_exclusive = parse_range(start, end)
    span = (last_exclusive - first).days
    if span > MAX_DAYS_BACK:
        raise HTTPException(
            status_code=422,
            detail=(
                f"range covers {span} days; this view holds at most {MAX_DAYS_BACK}. "
                "The user table can summarise a longer span."
            ),
        )
    _check_bin_hours(bin_hours)
    return Calendar(first, last_exclusive - timedelta(days=1), bin_hours)


# --- htcondordb ---------------------------------------------------------------


def _query_sync(sql: str, params: Sequence[Any]) -> list[tuple]:
    """One statement on a connection of its own.

    The driver blocks, and a connection is not shared across threads, so each
    query opens one in the worker thread that runs it. Connecting costs about
    50ms against ap2001, which is noise beside the queries themselves.
    """
    with htcondordb.connect(HTCONDORDB_ADDRESS, timeout=HTCONDORDB_TIMEOUT) as conn:
        return conn.execute(sql, tuple(params)).fetchall()


async def db_query(sql: str, params: Sequence[Any] = ()) -> list[tuple]:
    """Run one statement against htcondordb off the event loop.

    `?` is the driver's placeholder, and it finds them by scanning the text, so a
    `?` anywhere else in a statement -- `=?=` included -- is miscounted as one.
    Test for undefined with isUndefined() instead.

    A failure is a 502: htcondordb is the only source for these numbers, so there
    is no partial answer to fall back to.
    """
    started = monotonic()
    try:
        rows = await asyncio.to_thread(_query_sync, sql, params)
    except htcondordb.Error as error:
        logger.warning("htcondordb query failed after %.1fs: %s", monotonic() - started, error)
        raise HTTPException(status_code=502, detail=f"htcondordb query failed: {error}")
    logger.info("htcondordb: %d rows in %.2fs: %.120s", len(rows), monotonic() - started, sql)
    return rows


# Grouping by these three stays on the archive's columnar path; see "What it
# costs" in the module note.
_TERMINAL_KEYS = (
    f"ClusterId, time_bucket(QDate, '{BUCKET}'), time_bucket(EnteredCurrentStatus, '{BUCKET}')"
)
# Start times put a query on the per-record path, so only the day summary, which
# cannot do without them, asks for these.
_STARTED_KEYS = (
    f"ClusterId, JobStatus, time_bucket(QDate, '{BUCKET}'), "
    f"time_bucket(JobStartDate, '{BUCKET}'), time_bucket(EnteredCurrentStatus, '{BUCKET}')"
)


def _owner_history(owner: str, calendar: Calendar, snapshot: int) -> tuple[str, list[Any]]:
    """The WHERE clause every per-owner history query shares, and its values.

    The lower bound on EnteredHistoryTime is exact rather than a margin: a job
    open inside the window finished inside or after it, or was placed inside it,
    and either way entered history no earlier than the window opened. It is also
    what lets the archive skip every segment older than the window.

    The upper bound is the moment the live queue was read, so history and the
    queue describe one instant: a job that left the queue after the read is still
    counted as live, and not a second time as finished.
    """
    return (
        "Owner == ? && EnteredHistoryTime >= ? && EnteredHistoryTime < ?",
        [owner, calendar.start_sec, snapshot],
    )


async def fetch_terminal_groups(
    owner: str, calendar: Calendar, snapshot: int
) -> dict[tuple[int, bool, int, int], int]:
    """Finished jobs open inside the window, counted by (cluster, removed,
    queued hour, ended hour).

    Removed and finished are asked for separately rather than grouped by
    JobStatus, because a fourth group key falls off the columnar path. The end is
    EnteredCurrentStatus for both: on a terminal record it is when the job reached
    that state, and unlike CompletionDate it is set on removed jobs too.
    """
    where, params = _owner_history(owner, calendar, snapshot)

    async def one(removed: bool) -> tuple[bool, list[tuple]]:
        status = f"JobStatus {'==' if removed else '!='} {REMOVED_STATUS}"
        rows = await db_query(
            f"SELECT {_TERMINAL_KEYS}, COUNT(*) FROM {HISTORY_TABLE} "
            f"WHERE {where} && {status} GROUP BY {_TERMINAL_KEYS}",
            params,
        )
        return removed, rows

    groups: dict[tuple[int, bool, int, int], int] = {}
    for removed, rows in await asyncio.gather(one(True), one(False)):
        for cluster_id, queued_at, ended_at, count in rows:
            cluster = _as_int(cluster_id)
            if cluster is None or not count or not calendar.open_inside(queued_at, ended_at):
                continue
            key = (cluster, removed, int(queued_at), int(ended_at))
            groups[key] = groups.get(key, 0) + count
    return groups


async def fetch_started_groups(
    owner: str, calendar: Calendar, snapshot: int
) -> dict[tuple[int, bool, int, int, int], int]:
    """Finished jobs that ever ran, counted by (cluster, removed, queued hour,
    started hour, ended hour).

    time_bucket drops a record whose JobStartDate is undefined, so jobs that
    never ran are not here; never_started recovers them.
    """
    where, params = _owner_history(owner, calendar, snapshot)
    rows = await db_query(
        f"SELECT {_STARTED_KEYS}, COUNT(*) FROM {HISTORY_TABLE} WHERE {where} GROUP BY {_STARTED_KEYS}",
        params,
    )
    groups: dict[tuple[int, bool, int, int, int], int] = {}
    for cluster_id, status, queued_at, started_at, ended_at, count in rows:
        cluster = _as_int(cluster_id)
        if cluster is None or not count or not calendar.open_inside(queued_at, ended_at):
            continue
        key = (cluster, _as_int(status) == REMOVED_STATUS, int(queued_at), int(started_at), int(ended_at))
        groups[key] = groups.get(key, 0) + count
    return groups


def never_started(
    terminal: dict[tuple[int, bool, int, int], int],
    started: dict[tuple[int, bool, int, int, int], int],
) -> dict[tuple[int, bool, int, int], int]:
    """Finished jobs that never ran, per terminal group: every job in the group
    less the ones that ran.

    Subtraction rather than a query, because testing JobStartDate for undefined
    took nearly a minute for a busy owner, and these two queries are already
    paid for. Both read the same snapshot, so they count the same records; a
    negative difference could only come from a record ingested between them, and
    is clamped rather than reported as negative jobs.
    """
    ran: dict[tuple[int, bool, int, int], int] = {}
    for (cluster, removed, queued_at, _, ended_at), count in started.items():
        key = (cluster, removed, queued_at, ended_at)
        ran[key] = ran.get(key, 0) + count
    remainder: dict[tuple[int, bool, int, int], int] = {}
    for key, total in terminal.items():
        rest = total - ran.get(key, 0)
        if rest > 0:
            remainder[key] = rest
    return remainder


async def fetch_window_batches(owner: str, calendar: Calendar, snapshot: int) -> list[tuple]:
    """(cluster, batch name, jobs) from the proc-0 record of every cluster that
    finished one inside the window.

    One job per cluster rather than all of them: JobBatchName is on only some
    records, which puts a query over all of them on the per-record path, and
    condor_submit stamps one name on a whole submission anyway (see
    resolve_cluster_batches). Proc 0 is the one every cluster has.
    """
    where, params = _owner_history(owner, calendar, snapshot)
    return await db_query(
        f"SELECT ClusterId, JobBatchName, COUNT(*) FROM {HISTORY_TABLE} "
        f"WHERE {where} && ProcId == 0 GROUP BY ClusterId, JobBatchName",
        params,
    )


async def tally_history_batches(
    tally: dict[int, dict[str, int]], owner: str, window_rows: list[tuple], clusters: set[int]
) -> None:
    """Fold the window's proc-0 batch names into `tally`, then look up the rest.

    A cluster can be in the window without its proc 0: a long cluster whose
    first job finished before the window opened. Those are asked for by
    ClusterId, which the archive zone-maps, so the lookup skips straight to the
    segments that hold them instead of scanning the owner's whole history.
    Clusters already tallied, from the window or from the live queue, are not
    asked for again.
    """
    for cluster_id, name, count in window_rows:
        note_batch(tally, cluster_id, group_key(name), count)

    missing = {cluster for cluster in clusters if cluster not in tally}
    if not missing:
        return
    rows = await db_query(
        f"SELECT ClusterId, JobBatchName, COUNT(*) FROM {HISTORY_TABLE} "
        "WHERE Owner == ? && ProcId == 0 && ClusterId >= ? && ClusterId <= ? "
        "GROUP BY ClusterId, JobBatchName",
        [owner, min(missing), max(missing)],
    )
    for cluster_id, name, count in rows:
        if _as_int(cluster_id) in missing:
            note_batch(tally, cluster_id, group_key(name), count)


# --- Live queue ---------------------------------------------------------------


async def query_live_jobs(owner: str) -> tuple[dict[str, dict], list[str], int]:
    """This owner's live jobs, keyed "<cluster>.<proc>", any errors, and the
    moment they were read.

    The read time is the snapshot every history query of the same request is
    bounded by (see _owner_history). Jobs that already have a history record
    from the last LIVE_OVERLAP_SECONDS are dropped here: the queue and history
    are synced separately, so a job that has just finished can briefly be in
    both, and it belongs to history.

    A failure is reported rather than fatal. The live queue is the only source
    for jobs that have not finished, so losing it means an understatement, not a
    wrong answer -- and an understated page beats no page at all.

    Not window-specific: the queue is the same queue whichever week is being
    looked at, so it is read once and narrowed by live_ads_in_window.
    """
    snapshot = int(epoch_now())
    try:
        rows, recent = await asyncio.gather(
            db_query(
                f"SELECT {', '.join(LIVE_ATTRS)} FROM {JOBS_TABLE} WHERE Owner == ? && ProcId >= 0",
                [owner],
            ),
            db_query(
                f"SELECT ClusterId, ProcId FROM {HISTORY_TABLE} "
                "WHERE Owner == ? && EnteredHistoryTime >= ? && EnteredHistoryTime < ?",
                [owner, snapshot - LIVE_OVERLAP_SECONDS, snapshot],
            ),
        )
    except HTTPException as error:
        logger.warning("Live queue read from %s failed: %s", HTCONDORDB_SCHEDD, error.detail)
        return {}, [f"{HTCONDORDB_SCHEDD}: {error.detail}"], snapshot

    finished = {(_as_int(cluster), _as_int(proc)) for cluster, proc in recent}
    jobs: dict[str, dict] = {}
    superseded = 0
    for row in rows:
        job = dict(zip(LIVE_ATTRS, row))
        key = (_as_int(job["ClusterId"]), _as_int(job["ProcId"]))
        if key in finished:
            superseded += 1
            continue
        jobs[f"{key[0]}.{key[1]}"] = job
    if superseded:
        logger.info("%d live jobs superseded by a history record", superseded)
    return jobs, [], snapshot


def live_ads_in_window(ads: dict[str, dict], calendar: Calendar) -> dict[str, dict]:
    """The live jobs that were open at some point inside the window.

    A live job is open now, so it overlaps any window that closes after it was
    placed: the only test is QDate before the window's end. A job placed after a
    past window closed was not there yet and is left out, which is what keeps a
    past week's census from counting this week's submissions.

    Jobs with no readable QDate are kept. Dropping a job for a missing attribute
    would understate the queue, and the aggregators already treat an unknown
    placement as "before the window".
    """
    selected: dict[str, dict] = {}
    for key, ad in ads.items():
        queued_at = _as_seconds(ad.get("QDate"))
        if queued_at is None or queued_at < calendar.end_sec:
            selected[key] = ad
    return selected


async def fetch_live_jobs(owner: str, calendar: Calendar) -> tuple[dict[str, dict], list[str], int]:
    """This owner's live jobs that overlap the window, any errors, and the
    snapshot time to bound history by.

    The read is held for CACHE_SECONDS and narrowed to the window here. A
    calendar month asked for as five weekly windows costs one read of the queue
    rather than five -- and the lock inside the cache means the five arriving
    together still cost one. Every window served from one read shares its
    snapshot too, so they agree with each other about which jobs had finished.
    """
    jobs, errors, snapshot = await _cached_in(
        _live_cache, _live_cache_locks, ("live", owner),
        CACHE_SECONDS, LIVE_CACHE_MAX_ENTRIES, lambda: query_live_jobs(owner),
    )
    return live_ads_in_window(jobs, calendar), errors, snapshot


# --- Batch names --------------------------------------------------------------


def note_batch(tally: dict[int, dict[str, int]], cluster_id: Any, raw_name: Any, count: int) -> None:
    """Record `count` jobs of one cluster carrying one batch name."""
    if not count:
        return
    try:
        cluster = int(cluster_id)
    except (TypeError, ValueError):
        return
    key = NO_BATCH if raw_name in (None, "") else str(raw_name)
    counts = tally.setdefault(cluster, {})
    counts[key] = counts.get(key, 0) + count


def resolve_cluster_batches(tally: dict[int, dict[str, int]]) -> dict[int, str]:
    """One batch name per cluster, from per-cluster tallies of (name -> job count).

    JobBatchName is a per-job attribute, so in principle one cluster's jobs can
    disagree. In practice `condor_submit -batch-name` stamps a whole submission
    and the interesting relation runs the other way: one batch spans many
    clusters. That is what makes it safe to build batch groups by summing whole
    clusters, which keeps the payload small and the arithmetic exact.

    The assumption is checked rather than trusted: a cluster whose jobs carry
    more than one name is logged with its split, so this is visible instead of
    silently filing the cluster under whichever name happened to win.
    """
    dominant: dict[int, str] = {}
    mixed: list[str] = []
    for cluster_id, counts in tally.items():
        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if not ranked:
            continue
        dominant[cluster_id] = ranked[0][0]
        if len(ranked) > 1:
            total = sum(count for _, count in ranked)
            share = ranked[0][1] / total * 100
            mixed.append(f"cluster {cluster_id}: {len(ranked)} names, most common covers {share:.1f}%")
    if mixed:
        logger.warning(
            "%d cluster(s) carry more than one JobBatchName; each is filed under its most "
            "common name: %s", len(mixed), "; ".join(mixed[:20]),
        )
    return dominant


def publish_batch(raw_name: str) -> tuple[str, str]:
    """The published identity of a batch: the id the viewer groups on, and the
    text it shows. Real names, unlike the public bake -- the reader owns these
    jobs and picking their own batch out of a list is the whole point."""
    if raw_name == NO_BATCH:
        return "none", "(no batch name)"
    return raw_name, raw_name


def build_batch_list(members: dict[str, dict]) -> list[dict]:
    """One entry per batch, with the clusters that make it up and their summed
    total: the viewer needs the membership to filter and the total to label the
    picker."""
    batches = [
        {
            "id": entry["id"],
            "name": entry["name"],
            "total": entry["total"],
            "clusters": sorted(entry["clusters"]),
        }
        for entry in members.values()
    ]
    batches.sort(key=lambda batch: (-batch["total"], str(batch["id"])))
    return batches


# --- Owner resolution ---------------------------------------------------------


def _short_host(name: Optional[str]) -> str:
    """"ap2001.chtc.wisc.edu" and "ap2001" are the same node; submit_nodes holds both forms."""
    return (name or "").strip().lower().split(".")[0]


# The access point whose jobs these endpoints can see: the one htcondordb is
# pointed at. Until the other APs' databases are reachable, a user who does not
# submit there is refused with a message rather than shown an empty calendar
# that looks like they never ran anything.
SUPPORTED_AP = _short_host(HTCONDORDB_SCHEDD)


async def check_on_supported_ap(session, user_id: int, netid: str) -> None:
    """Refuse a user who has no access to the AP the job history is read from.

    Access is what /users/{id}/submit_nodes reports (group membership), so a user
    on ap2001 and another AP passes, and sees their ap2001 jobs only.
    """
    rows = await session.execute(select(UserSubmitView.name).where(UserSubmitView.user_id == user_id))
    nodes = sorted({name for name in rows.scalars() if name})
    if any(_short_host(name) == SUPPORTED_AP for name in nodes):
        return
    where = f"Their access points are: {', '.join(nodes)}." if nodes else "They have no access points on record."
    raise HTTPException(
        status_code=409,
        detail=(
            f"Job history is only available for {SUPPORTED_AP} for now, "
            f"and {netid} is not a {SUPPORTED_AP} user. {where}"
        ),
    )


async def resolve_owner(session, requested: Optional[str], user_token, admin: bool) -> tuple[str, int]:
    """The netid whose jobs are being asked about, and that user's id.

    A user may only ask about themselves; an admin may name anyone. The netid is
    what HTCondor records as Owner, which is why it is the join between this
    application's users and the pool's jobs. Either way the owner must be on
    SUPPORTED_AP (see check_on_supported_ap).
    """
    netid, user_id = await _resolve_owner(session, requested, user_token, admin)
    await check_on_supported_ap(session, user_id, netid)
    return netid, user_id


async def _resolve_owner(session, requested: Optional[str], user_token, admin: bool) -> tuple[str, int]:
    if requested is None:
        if user_token is None:
            raise HTTPException(
                status_code=400,
                detail="owner is required when authenticating with an API token",
            )
        user = await session.get(User, user_token.user_id)
        if user is None or not user.netid:
            raise HTTPException(
                status_code=409,
                detail="This account has no netid on record, so its jobs cannot be identified",
            )
        return user.netid, user.id

    if not admin:
        user = await session.get(User, user_token.user_id) if user_token else None
        if user is None or user.netid != requested:
            raise HTTPException(
                status_code=403,
                detail="Non-admin user requesting job data that doesn't belong to them.",
            )
        return user.netid, user.id

    user = (await session.execute(select(User).where(User.netid == requested))).scalars().first()
    if user is None:
        raise HTTPException(status_code=404, detail=f"No user with netid {requested}")
    return user.netid, user.id


# --- Response cache -----------------------------------------------------------

_cache: dict[tuple, tuple[float, Any]] = {}
_cache_locks: dict[tuple, asyncio.Lock] = {}

# Days get their own store rather than sharing the one above. A single range
# admits dozens of day entries at once, and they are small; letting them compete
# with the per-owner payloads for the same 64 slots would evict the expensive
# thing to make room for the cheap one. Sized to hold well over a year, so the
# ranges a reader moves between stay warm.
_day_cache: dict[tuple, tuple[float, Any]] = {}
_day_cache_locks: dict[tuple, asyncio.Lock] = {}
DAY_CACHE_MAX_ENTRIES = 512

# The live queue, per owner. Separate from the payload cache for the same reason
# the days are: a payload is one window's answer, while the queue is shared by
# every window of that owner, and the two would otherwise evict each other.
_live_cache: dict[tuple, tuple[float, Any]] = {}
_live_cache_locks: dict[tuple, asyncio.Lock] = {}
LIVE_CACHE_MAX_ENTRIES = 64


async def _cached_in(
    store: dict,
    locks: dict,
    key: tuple,
    ttl: float,
    max_entries: int,
    build: Callable[[], Awaitable[Any]],
) -> Any:
    """Serve `key` from `store` when it is fresh, otherwise build it once.

    The lock matters as much as the cache: without it, the several requests a
    page makes on load would each start their own fan-out across every schedd.
    """
    if ttl <= 0:
        return await build()

    now = monotonic()
    hit = store.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]

    lock = locks.setdefault(key, asyncio.Lock())
    async with lock:
        # Another waiter may have built it while this one queued for the lock.
        hit = store.get(key)
        if hit and monotonic() - hit[0] < ttl:
            return hit[1]

        value = await build()
        store[key] = (monotonic(), value)

        # Bounded, and evicting by age keeps whatever is being refreshed often.
        if len(store) > max_entries:
            for stale, _ in sorted(store.items(), key=lambda item: item[1][0])[:len(store) - max_entries]:
                store.pop(stale, None)
                locks.pop(stale, None)
        return value


async def cached(key: tuple, build: Callable[[], Awaitable[dict]]) -> dict:
    """The per-owner payload cache: one short TTL for every entry."""
    return await _cached_in(_cache, _cache_locks, key, CACHE_SECONDS, CACHE_MAX_ENTRIES, build)


async def cached_day(key: tuple, ttl: float, build: Callable[[], Awaitable[Any]]) -> Any:
    """The per-day cache, whose TTL is the caller's to choose.

    A day that has already ended is settled history and can be held for hours;
    today cannot. See `day_cache_ttl`.
    """
    return await _cached_in(_day_cache, _day_cache_locks, key, ttl, DAY_CACHE_MAX_ENTRIES, build)


# --- Series payload -----------------------------------------------------------


def group_key(value: Any) -> Any:
    """A GROUP BY key as plain text.

    htcondordb hands back string group keys as ClassAd literals -- the netid
    alice arrives as '"alice"', quotes and all -- while the same attribute in a
    plain SELECT list arrives as 'alice'. Numbers and undefined (None) come back
    as themselves. So every string key read from a grouped query goes through
    here before it is shown or compared with the live queue's values.
    """
    if isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] == '"':
        return _CLASSAD_ESCAPE.sub(r"\1", value[1:-1])
    return value


# Inside a ClassAd string literal a backslash escapes the next character; the
# two that matter for names are \" and \\.
_CLASSAD_ESCAPE = re.compile(r'\\(["\\])')


def _as_seconds(value: Any) -> Optional[float]:
    """An epoch-seconds attribute as a number, or None when it is absent or junk."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    seconds = _as_seconds(value)
    return None if seconds is None else int(seconds)


def _sparse(dense: list[int]) -> list[tuple[int, int]]:
    """Sparse [binIndex, count] pairs from a dense array, in bin order."""
    return [(index, count) for index, count in enumerate(dense) if count > 0]


def _zeros(length: int) -> array:
    """A zeroed counter array. 64-bit: a busy owner's day can run to millions of
    transitions, and an overflow here would surface as a 500 rather than a wrong
    number, but neither is worth the four bytes saved."""
    return array("q", bytes(8 * length))


def _sources(live_jobs: int, errors: list[str]) -> dict:
    """Where the numbers came from, under the keys the viewer already reads.

    `adstash` and `condorQ` are names from when the two halves came from
    Elasticsearch and condor_q. They are kept because they are the viewer's wire
    contract; both halves now come from the same htcondordb.
    """
    return {
        "adstash": {"host": HTCONDORDB_ADDRESS, "index": HISTORY_TABLE},
        "condorQ": {
            "pool": CONDOR_POOL,
            "schedd": HTCONDORDB_SCHEDD,
            "schedds": [HTCONDORDB_SCHEDD],
            "liveAds": live_jobs,
            "errors": errors,
        },
    }


async def build_job_series(
    owner: str, days_back: int, bin_hours: int,
    start: Optional[str] = None, end: Optional[str] = None,
) -> dict:
    """Per-cluster placements and terminal transitions, binned across the window.

    Three series per cluster plus an opening census is exactly what a cumulative
    census of any day needs: of every job in play that day (active when it
    opened, plus placed so far), how many are still active, completed, or
    removed. The day slicing, running sums and percentages are the client's.

    Needs no start times, so every history query here stays on the fast path.
    """
    calendar = (
        build_calendar_for_range(start, end, bin_hours)
        if start and end
        else build_calendar(days_back, bin_hours)
    )
    batch_tally: dict[int, dict[str, int]] = {}
    per_cluster: dict[int, dict] = {}

    def series_for(cluster: int) -> dict:
        entry = per_cluster.get(cluster)
        if entry is None:
            entry = per_cluster[cluster] = {
                "openingActive": 0,
                "placed": [0] * calendar.total_bins,
                "completed": [0] * calendar.total_bins,
                "removed": [0] * calendar.total_bins,
            }
        return entry

    # The queue first: its read time is the snapshot history is bounded by.
    live_jobs, live_errors, snapshot = await fetch_live_jobs(owner, calendar)
    terminal, batch_rows = await asyncio.gather(
        fetch_terminal_groups(owner, calendar, snapshot),
        fetch_window_batches(owner, calendar, snapshot),
    )

    # 1. Live queue: the only source for jobs that have not finished.
    for job in live_jobs.values():
        cluster = _as_int(job.get("ClusterId"))
        if cluster is None:
            continue
        note_batch(batch_tally, cluster, job.get("JobBatchName"), 1)
        entry = series_for(cluster)
        placed_bin = calendar.bin_index(job.get("QDate"))
        queued_at = _as_seconds(job.get("QDate"))
        if placed_bin >= 0:
            entry["placed"][placed_bin] += 1
        elif queued_at is not None and queued_at < calendar.start_sec:
            # Placed before the window and still live now: in play throughout.
            entry["openingActive"] += 1

    # 2. Finished jobs. Every group was open inside the window, so one placed
    #    before it finished inside or after it, and was in play when it opened.
    for (cluster, removed, queued_at, ended_at), count in terminal.items():
        entry = series_for(cluster)
        if queued_at < calendar.start_sec:
            entry["openingActive"] += count
        else:
            entry["placed"][calendar.bin_index(queued_at)] += count
        end_bin = calendar.bin_index(ended_at)
        if end_bin >= 0:
            (entry["removed"] if removed else entry["completed"])[end_bin] += count

    await tally_history_batches(batch_tally, owner, batch_rows, {key[0] for key in terminal})

    # 3. Publish, largest cluster first so batch membership is built in a
    #    deterministic order, then keyed by cluster for the viewer's picker.
    batch_of = resolve_cluster_batches(batch_tally)
    ranked = [
        (cluster, entry, entry["openingActive"] + sum(entry["placed"]))
        for cluster, entry in per_cluster.items()
    ]
    ranked = [
        item for item in ranked
        if item[2] > 0 or any(item[1]["completed"]) or any(item[1]["removed"])
    ]
    ranked.sort(key=lambda item: (-item[2], item[0]))

    members: dict[str, dict] = {}
    series = []
    for cluster, entry, total in ranked:
        batch_id, batch_name = publish_batch(batch_of.get(cluster, NO_BATCH))
        member = members.setdefault(
            batch_id, {"id": batch_id, "name": batch_name, "total": 0, "clusters": set()}
        )
        member["total"] += total
        member["clusters"].add(cluster)
        series.append({
            "cluster": cluster,
            "batch": batch_id,
            "total": total,
            "openingActive": entry["openingActive"],
            "placed": _sparse(entry["placed"]),
            "completed": _sparse(entry["completed"]),
            "removed": _sparse(entry["removed"]),
        })
    series.sort(key=lambda item: item["cluster"])

    return {
        "owner": owner,
        "anonymized": False,
        "generatedAt": datetime.now(TZ).isoformat(),
        "timezone": TIMEZONE,
        "days": calendar.days,
        "binHours": calendar.bin_hours,
        "binsPerDay": calendar.bins_per_day,
        "series": series,
        "batches": build_batch_list(members),
        "sources": _sources(len(live_jobs), live_errors),
    }


# --- Day summary --------------------------------------------------------------


class _DayAggregator:
    """Folds every job into the per-day counters the viewer reads.

    Counters are flat arrays indexed by cluster slot, so adding a cluster costs
    no rehashing per job:

      states[queueDay][asOfDay * 4 + state]
          four-state breakdown of the cohort queued on queueDay, as of asOfDay.
          Kept per queue day rather than as one D x D block because most
          clusters submit on one or two days and the empty rows are the bulk of
          that block.
      pre_states["YYYY-MM-DD"][asOfDay * 4 + state]
          the same, for cohorts placed before the window opened, keyed by their
          real placement day. Only the jobs still open when the window opened
          are here -- the ones that finished earlier were never selected -- so
          such a cohort's numbers describe its survivors, and the window that
          contains its placement day is the one that has the whole cohort.
      activity[day * 3 + {0 started, 1 completed, 2 removed}]
          transitions that happened on `day`, whatever day the job was queued.
    """

    def __init__(self, calendar: Calendar):
        self.calendar = calendar
        self.D = len(calendar)
        self.cluster_slot: dict[int, int] = {}
        self.cluster_ids: list[int] = []
        # ClusterId -> {raw batch name: jobs}. Tallied rather than assigned so a
        # cluster whose jobs disagree can be reported.
        self.batch_tally: dict[int, dict[str, int]] = {}
        self.states: list[dict[int, array]] = []
        self.pre_states: list[dict[str, array]] = []
        self.pre_totals: list[dict[str, int]] = []
        self.activity: list[array] = []
        self.changed: list[array] = []   # distinct jobs that moved that day
        self.flows: list[array] = []     # Sankey edge weights
        # Jobs sitting in each non-terminal state at the END of each day, across
        # every job in scope including those placed before the window. This is
        # what lets one day's Sankey hand off to the next: without it a job still
        # running at midnight disappears from the diagram and reappears with no
        # connecting ribbon.
        self.end_placed: list[array] = []
        self.end_active: list[array] = []
        # State at the instant the window opens, i.e. the "day -1" census.
        # Without it the first day has no measurable carry-in and any period
        # starting there has to guess its opening backlog.
        self.start_placed: list[int] = []
        self.start_active: list[int] = []
        self.cohort_totals: list[array] = []
        self.held_live = 0
        self.placed_before_window = 0
        self.counted = 0

    def _slot_for(self, cluster_id: int) -> int:
        slot = self.cluster_slot.get(cluster_id)
        if slot is None:
            slot = self.cluster_slot[cluster_id] = len(self.cluster_ids)
            self.cluster_ids.append(cluster_id)
            D = self.D
            self.states.append({})
            self.pre_states.append({})
            self.pre_totals.append({})
            self.activity.append(_zeros(D * 3))
            self.changed.append(_zeros(D))
            self.flows.append(_zeros(D * FLOW_COUNT))
            self.end_placed.append(_zeros(D))
            self.end_active.append(_zeros(D))
            self.start_placed.append(0)
            self.start_active.append(0)
            self.cohort_totals.append(_zeros(D))
        return slot

    def add(
        self,
        cluster_id: int,
        queue_day: int,
        *,
        run_from_day: int = -1,
        started_day: int = -1,
        end_day: int = -1,
        end_state: int = STATE_COMPLETED,
        count: int = 1,
        ever_ran: Optional[bool] = None,
        has_end: Optional[bool] = None,
        queue_key: Optional[str] = None,
    ) -> None:
        """Fold one bucket of identical jobs in.

        Day indices come from Calendar.day_index_clamped: -1 means before the
        window opened, D (the number of days) means at or after it closed, and
        anything in between is a day of the window. The two outside values are
        not interchangeable -- a job that starts after the window was queued all
        the way through it, while one that started before it was running -- so
        every test below asks which side it is on.

        queue_day     day index the job was submitted, or -1 if before the window
        queue_key     the real "YYYY-MM-DD" it was submitted, used when queue_day
                      is -1 to file the job under a cohort of its own placement
                      day. None when the placement day is unknown.
        run_from_day  day index from which to paint it Running, -1 (never inside
                      the window, or before it: see ever_ran) or D. Distinct from
                      started_day because a live ad that ran and was evicted back
                      to Idle has a JobStartDate but is not running now, and the
                      four-state model cannot say "ran, then queued again".
        started_day   day index of JobStartDate for the transition count, -1 or D
        end_day       day index it reached its terminal state, -1 or D
        end_state     STATE_COMPLETED or STATE_REMOVED when it has an end
        count         how many identical jobs this represents
        ever_ran      whether the job ever ran, which is not the same as
                      started_day >= 0: a job that started before the window ran,
                      but has no in-window start day
        has_end       likewise, whether it reached a terminal state at all
        """
        if count <= 0:
            return
        D = self.D
        if ever_ran is None:
            ever_ran = started_day >= 0
        if has_end is None:
            has_end = end_day >= 0

        slot = self._slot_for(cluster_id)
        activity = self.activity[slot]
        changed = self.changed[slot]
        flows = self.flows[slot]

        def state_on(day: int) -> int:
            # Terminal from its end day, running from its start day, queued
            # before either. An end or start at D never arrives inside the loop.
            if end_day >= 0 and day >= end_day:
                return end_state
            if run_from_day >= 0 and day >= run_from_day:
                return STATE_RUNNING
            return STATE_QUEUED

        if queue_day < 0:
            # Placed before the window. Its transitions still land on the days
            # they happened, and it holds a place in the census; and when its
            # placement day is known it gets a cohort keyed by that day, so a
            # viewer merging several windows can carry the cohort across them.
            self.placed_before_window += count
            if queue_key is not None:
                totals = self.pre_totals[slot]
                totals[queue_key] = totals.get(queue_key, 0) + count
                states = self.pre_states[slot].get(queue_key)
                if states is None:
                    states = self.pre_states[slot][queue_key] = _zeros(D * STATE_COUNT)
                for day in range(D):
                    states[day * STATE_COUNT + state_on(day)] += count
        else:
            self.cohort_totals[slot][queue_day] += count
            self.counted += count

            states = self.states[slot].get(queue_day)
            if states is None:
                states = self.states[slot][queue_day] = _zeros(D * STATE_COUNT)

            # Walk the timeline once, from the queue day to the window edge.
            for day in range(queue_day, D):
                states[day * STATE_COUNT + state_on(day)] += count

        started_inside = 0 <= started_day < D
        ended_inside = 0 <= end_day < D

        # Per-transition counts. A job that started and finished the same day
        # lands on both lines, which is why these are not comparable to
        # `changed` below.
        if started_inside:
            activity[started_day * 3] += count
        if ended_inside:
            activity[end_day * 3 + (1 if end_state == STATE_COMPLETED else 2)] += count

        # Distinct jobs that moved at all on a given day. Every job in this
        # bucket shares the same start and end day, so collapsing them here
        # counts a start-and-finish-same-day job once rather than twice. Buckets
        # partition the corpus, so summing these across buckets stays a true
        # distinct-job count.
        if started_inside:
            changed[started_day] += count
        if ended_inside and end_day != started_day:
            changed[end_day] += count

        # End-of-day census. Runs over every job, including those placed before
        # the window -- omitting them would understate the carried-over backlog
        # by the entire pre-window population. A job that ended after the window
        # (end_day == D) holds its place on every day; only one that ended before
        # it opened was never here.
        end_placed = self.end_placed[slot]
        end_active = self.end_active[slot]
        queued_before_window = queue_day < 0     # QDate can only precede the window
        started_before_window = ever_ran and started_day < 0
        ended_before_window = has_end and end_day < 0
        if not ended_before_window:
            # The same test one step before day 0: what this job was doing at the
            # moment the window opened.
            if started_before_window:
                self.start_active[slot] += count
            elif queued_before_window:
                self.start_placed[slot] += count

            for day in range(D):
                # Terminal from its end day onward, so it holds no state after.
                if has_end and end_day >= 0 and day >= end_day:
                    break
                if started_before_window or (started_day >= 0 and day >= started_day):
                    end_active[day] += count
                elif queued_before_window or (queue_day >= 0 and day >= queue_day):
                    end_placed[day] += count
                # Otherwise the job does not exist yet on this day.

        # Sankey edges. "Placed Today" means placed on the same day as the
        # transition being drawn, so the same job can be Placed-Today in one
        # day's diagram and Placed-Before in the next day's.
        if started_inside:
            placed_today = queue_day == started_day
            slot_index = FLOW_PLACED_TODAY_ACTIVE if placed_today else FLOW_PLACED_BEFORE_ACTIVE
            flows[started_day * FLOW_COUNT + slot_index] += count
        if ended_inside:
            placed_today = queue_day == end_day
            if end_state == STATE_COMPLETED:
                if ever_ran:
                    # Finishing implies having run, so this normally leaves
                    # Active. A completion with no start at all is a data oddity;
                    # route it from Placed rather than inventing a run.
                    flows[end_day * FLOW_COUNT + FLOW_ACTIVE_COMPLETED] += count
                else:
                    slot_index = (
                        FLOW_PLACED_TODAY_COMPLETED if placed_today else FLOW_PLACED_BEFORE_COMPLETED
                    )
                    flows[end_day * FLOW_COUNT + slot_index] += count
            elif ever_ran:
                flows[end_day * FLOW_COUNT + FLOW_ACTIVE_REMOVED] += count
            else:
                # Removed straight out of the queue without ever running -- the
                # "skip Active" edge.
                slot_index = FLOW_PLACED_TODAY_REMOVED if placed_today else FLOW_PLACED_BEFORE_REMOVED
                flows[end_day * FLOW_COUNT + slot_index] += count

    def to_payload(self, owner: str, sources: dict) -> dict:
        """Shape the flat counters into the payload the viewer consumes."""
        days = self.calendar.days
        D = self.D

        # Stable, readable ordering: biggest clusters first. Clusters with no
        # cohort of either kind and no transition contribute nothing and are
        # dropped. A cluster whose jobs were all placed before the window and sat
        # idle through it stays: it has no activity, but it is the backlog.
        order = [
            (cluster_id, slot)
            for slot, cluster_id in enumerate(self.cluster_ids)
            if any(self.cohort_totals[slot]) or self.pre_totals[slot] or any(self.activity[slot])
        ]
        order.sort(key=lambda pair: (-sum(self.cohort_totals[pair[1]]), pair[0]))

        batch_of = resolve_cluster_batches(self.batch_tally)
        members: dict[str, dict] = {}

        cohorts: list[dict] = []
        activity_rows: list[dict] = []
        clusters: list[dict] = []
        # Separate from `activity`: a day can carry a backlog forward without
        # anything transitioning on it, so this cannot ride along on the
        # transition rows.
        carry: list[dict] = []

        for cluster_id, slot in order:
            totals = self.cohort_totals[slot]
            cluster_total = 0
            first_day: Optional[str] = None

            for queue_day in range(D):
                queued = totals[queue_day]
                if queued == 0:
                    continue
                cluster_total += queued
                if first_day is None:
                    first_day = days[queue_day]

                # Only days from the cohort's own queue day forward carry meaning.
                states = self.states[slot][queue_day]
                as_of = {
                    days[day]: (
                        states[day * STATE_COUNT],
                        states[day * STATE_COUNT + 1],
                        states[day * STATE_COUNT + 2],
                        states[day * STATE_COUNT + 3],
                    )
                    for day in range(queue_day, D)
                }
                cohorts.append({
                    "cluster": cluster_id,
                    "day": days[queue_day],
                    "queued": queued,
                    "asOf": as_of,
                })

            # Cohorts placed before the window, keyed by their real day. Every
            # day of the window carries meaning for these, since the cohort
            # already existed when it opened.
            for queue_key, queued in sorted(self.pre_totals[slot].items()):
                states = self.pre_states[slot][queue_key]
                cohorts.append({
                    "cluster": cluster_id,
                    "day": queue_key,
                    "queued": queued,
                    "asOf": {
                        days[day]: (
                            states[day * STATE_COUNT],
                            states[day * STATE_COUNT + 1],
                            states[day * STATE_COUNT + 2],
                            states[day * STATE_COUNT + 3],
                        )
                        for day in range(D)
                    },
                })
                if first_day is None or queue_key < first_day:
                    first_day = queue_key

            acts = self.activity[slot]
            changed = self.changed[slot]
            flows = self.flows[slot]
            for day in range(D):
                started, completed, removed = acts[day * 3], acts[day * 3 + 1], acts[day * 3 + 2]
                if not (started or completed or removed):
                    continue
                base = day * FLOW_COUNT
                activity_rows.append({
                    "cluster": cluster_id,
                    "day": days[day],
                    "started": started,
                    "completed": completed,
                    "removed": removed,
                    # `changed` is distinct jobs; the three lines above
                    # double-count a job that did more than one thing that day.
                    # Both are reported rather than reconciled because both are
                    # wanted: the calendar shows distinct jobs, the day detail
                    # shows every transition.
                    "changed": changed[day],
                    "flows": {
                        "placedTodayToActive": flows[base + FLOW_PLACED_TODAY_ACTIVE],
                        "placedBeforeToActive": flows[base + FLOW_PLACED_BEFORE_ACTIVE],
                        "activeToCompleted": flows[base + FLOW_ACTIVE_COMPLETED],
                        "activeToRemoved": flows[base + FLOW_ACTIVE_REMOVED],
                        "placedTodayToRemoved": flows[base + FLOW_PLACED_TODAY_REMOVED],
                        "placedBeforeToRemoved": flows[base + FLOW_PLACED_BEFORE_REMOVED],
                        "placedTodayToCompleted": flows[base + FLOW_PLACED_TODAY_COMPLETED],
                        "placedBeforeToCompleted": flows[base + FLOW_PLACED_BEFORE_COMPLETED],
                    },
                })

            # Day "-1": the opening state, keyed by a sentinel the viewer
            # resolves to "before the window".
            if self.start_placed[slot] or self.start_active[slot]:
                carry.append({
                    "cluster": cluster_id,
                    "day": WINDOW_START_DAY,
                    "placed": self.start_placed[slot],
                    "active": self.start_active[slot],
                })
            end_placed = self.end_placed[slot]
            end_active = self.end_active[slot]
            for day in range(D):
                if end_placed[day] or end_active[day]:
                    carry.append({
                        "cluster": cluster_id,
                        "day": days[day],
                        "placed": end_placed[day],
                        "active": end_active[day],
                    })

            batch_id, batch_name = publish_batch(batch_of.get(cluster_id, NO_BATCH))
            member = members.setdefault(
                batch_id, {"id": batch_id, "name": batch_name, "total": 0, "clusters": set()}
            )
            member["total"] += cluster_total
            member["clusters"].add(cluster_id)

            # `total` counts the jobs placed inside the window, so it adds up
            # across tiled windows. A cluster whose jobs were all placed before
            # the window still belongs in the picker if any of them were open
            # during it, so a total of 0 is legitimate here; its firstQueued then
            # names the earliest pre-window cohort.
            clusters.append({
                "id": cluster_id,
                "total": cluster_total,
                "firstQueued": first_day,
                "batch": batch_id,
            })

        return {
            "owner": owner,
            "anonymized": False,
            "generatedAt": datetime.now(TZ).isoformat(),
            "timezone": TIMEZONE,
            "days": days,
            # Hold is intentionally not a state; see the note at the top of this
            # module.
            "states": list(STATE_NAMES),
            "clusters": clusters,
            "batches": build_batch_list(members),
            "cohorts": cohorts,
            "activity": activity_rows,
            "carry": carry,
            "sources": sources,
            "counted": self.counted,
            "placedBeforeWindow": self.placed_before_window,
        }


async def build_job_day_summary(
    owner: str, days_back: int,
    start: Optional[str] = None, end: Optional[str] = None,
) -> dict:
    """Per-day cohort censuses, transition counts and flow edges for the window.

    Fully pre-aggregated: for every (cluster, queue-day) cohort this stores the
    four-state breakdown as of the end of every later day, so the client does no
    per-job arithmetic however many jobs the window holds.

    The joint distribution of (cluster, status, queue hour, start hour, end hour)
    is everything this needs: state as of any day D follows arithmetically from
    it -- terminal if the end is on or before D, else running if the start is,
    else queued. Asking for start hours is the one slow query in this module (see
    "What it costs"); the others run alongside it.
    """
    calendar = (
        build_calendar_for_range(start, end, DEFAULT_BIN_HOURS)
        if start and end
        else build_calendar(days_back, DEFAULT_BIN_HOURS)
    )
    aggregator = _DayAggregator(calendar)

    # The queue first: its read time is the snapshot history is bounded by.
    live_jobs, live_errors, snapshot = await fetch_live_jobs(owner, calendar)
    terminal, started, batch_rows = await asyncio.gather(
        fetch_terminal_groups(owner, calendar, snapshot),
        fetch_started_groups(owner, calendar, snapshot),
        fetch_window_batches(owner, calendar, snapshot),
    )

    # 1. Finished jobs that ran.
    for (cluster, removed, queued_at, started_at, ended_at), count in started.items():
        # Clamped: a start after the window closed must read as "queued
        # throughout", not as "running since before it".
        start_day = calendar.day_index_clamped(started_at)
        aggregator.add(
            cluster,
            calendar.day_index(queued_at),
            queue_key=calendar.day_key(queued_at),
            # A job that started before the window was running from its first
            # day. Left at -1 it would be painted queued, and a cohort's
            # queued/running split would disagree between a window and the one
            # before it.
            run_from_day=0 if start_day < 0 else start_day,
            started_day=start_day,
            end_day=calendar.day_index_clamped(ended_at),
            end_state=STATE_REMOVED if removed else STATE_COMPLETED,
            count=count,
            ever_ran=True,
            has_end=True,
        )

    # 2. Finished jobs that never ran: removed straight out of the queue, the
    #    "skip Active" edge of the Sankey.
    for (cluster, removed, queued_at, ended_at), count in never_started(terminal, started).items():
        aggregator.add(
            cluster,
            calendar.day_index(queued_at),
            queue_key=calendar.day_key(queued_at),
            run_from_day=-1,
            started_day=-1,
            end_day=calendar.day_index_clamped(ended_at),
            end_state=STATE_REMOVED if removed else STATE_COMPLETED,
            count=count,
            ever_ran=False,
            has_end=True,
        )

    # 3. Whatever is still only in the queue.
    for job in live_jobs.values():
        cluster = _as_int(job.get("ClusterId"))
        if cluster is None:
            continue
        status = _as_int(job.get("JobStatus"))
        if status == 5:
            aggregator.held_live += 1
        started_at = _as_seconds(job.get("JobStartDate"))
        # Clamped for the same reason as the finished jobs: a past window can
        # hold a job that only started after it closed.
        started_day = calendar.day_index_clamped(started_at)
        note_batch(aggregator.batch_tally, cluster, job.get("JobBatchName"), 1)
        aggregator.add(
            cluster,
            calendar.day_index(job.get("QDate")),
            queue_key=calendar.day_key(job.get("QDate")),
            # Only a Running job (JobStatus 2) is actually running; Idle and
            # Held both read as Queued. One that started before the window has
            # been running since its first day.
            run_from_day=max(started_day, 0) if status == 2 else -1,
            started_day=started_day,
            end_day=-1,
            # A live job knows whether it ever ran even when the start fell
            # before the window.
            ever_ran=bool(started_at and started_at > 0),
        )
    if aggregator.held_live:
        logger.warning(
            "%d live jobs are Held (JobStatus 5); counted as Queued because the history "
            "records carry no hold data to pair them with.", aggregator.held_live,
        )

    await tally_history_batches(aggregator.batch_tally, owner, batch_rows, {key[0] for key in terminal})

    sources = _sources(len(live_jobs), live_errors)
    sources["adstash"]["terminalRecords"] = (
        aggregator.counted + aggregator.placed_before_window - len(live_jobs)
    )
    sources["condorQ"]["stillQueued"] = len(live_jobs)
    return aggregator.to_payload(owner, sources)


# --- A range of days, by user -------------------------------------------------
#
# One row per user who finished a job in the requested range, busiest first, so a
# facilitator can see who is worth looking at before opening anyone's calendar.
#
# "In the range" means the job reached a terminal state in it, not that it was
# submitted in it: EnteredCurrentStatus is set on Completed and Removed records
# alike, it is what the calendar's end bars already key on, and it partitions the
# window cleanly, which QDate would not -- a job submitted on one day and
# finished on another has one end but its whole run to attribute.


def parse_range(start: str, end: str) -> tuple[date, date]:
    """`YYYY-MM-DD` bounds as dates, half-open, rejecting anything unusable.

    `end` is exclusive, which is what makes consecutive ranges tile without
    double-counting the day they meet.
    """
    try:
        first = date.fromisoformat(start)
        last = date.fromisoformat(end)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422, detail="start and end must look like YYYY-MM-DD"
        )

    if last <= first:
        raise HTTPException(status_code=422, detail="end must be after start")

    span = (last - first).days
    if span > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"range covers {span} days; the most that may be asked for is {MAX_RANGE_DAYS}",
        )

    today = datetime.now(TZ).date()
    if first > today:
        raise HTTPException(status_code=422, detail=f"{start} is in the future")

    return first, last


def range_days(start: date, end: date) -> list[date]:
    """Every day in a half-open range.

    The day, not the week, is the unit this endpoint queries and caches. Days
    tile an arbitrary range exactly, which whole weeks cannot, and one day of
    ap2001's history answers in about a second, so no single query comes close to
    HTCONDORDB_TIMEOUT however long the range.
    """
    return [start + timedelta(days=index) for index in range((end - start).days)]


def day_cache_ttl(day: date) -> float:
    """How long one day's numbers may be held.

    A day that has already ended is settled history and is worth holding for
    hours. Today is not, and gets the same short TTL as every other live payload.
    Ranges overlap constantly -- every shift of the picker reuses most of its
    days -- which is what makes this cache earn its keep.
    """
    if CACHE_SECONDS <= 0:
        return 0.0
    ended = day < datetime.now(TZ).date()
    return DAY_CACHE_SECONDS_PAST if ended else CACHE_SECONDS


# The per-user figures a day contributes. Every one is a count or a sum, both of
# which add across any number of days exactly -- that is what lets a range be
# assembled out of cached days. Anything that cannot be merged this way (a median,
# a percentile, a distinct count) does not belong in this table: it would have to
# be asked for range-wide, which costs more than everything here combined.
#
_DAY_COUNTS = ("removed", "held", "failed", "retried")
_DAY_SUMS = (
    "slotSeconds", "wallSeconds", "userCpu", "sysCpu",
    "memoryUsed", "memoryRequested", "diskUsed", "diskRequested", "cpusRequested",
)

# A day is read in three queries rather than one, because htcondordb cannot sum
# an attribute that some records hold as an expression rather than a number. When
# it meets one, every owner whose sum touched it comes back merged into a single
# row with no Owner at all -- and RequestMemory and RequestDisk are expressions
# on thousands of CHTC's records a day. It happens whenever a query falls to the
# per-record path, which any FILTER or partly-present attribute forces, so those
# two are each asked for alone, where a failure costs only that one figure.
#
# Every bound shares the day's WHERE clause. EnteredHistoryTime is never before
# EnteredCurrentStatus on a terminal record, so bounding it by the day's start
# loses nothing and lets the archive skip every older segment.
_USER_DAY_WHERE = (
    f"FROM {HISTORY_TABLE} "
    "WHERE EnteredHistoryTime >= ? && EnteredCurrentStatus >= ? && EnteredCurrentStatus < ? "
    "GROUP BY Owner"
)

# Everything that sums cleanly, in the order fetch_user_day reads it back.
#
# `held` counts records carrying a positive NumHolds: HTCondor only writes the
# attribute onto a job that was actually held. `failed` is a non-zero ExitCode;
# a removed job has none, and an undefined comparison counts as false.
#
# Memory used is summed from ResidentSetSize (KiB) rather than MemoryUsage (MB),
# which is an expression over ResidentSetSize on these records and so cannot be
# summed at all. The two differ by MemoryUsage rounding each job up to a whole
# MB, under a megabyte a job.
#
# Slot time is wall time already multiplied by the cores the job provisioned, and
# it is written on every record, so the core-hours column is a plain sum.
_USER_DAY_FIELDS = (
    "removed", "held", "failed", "retried",
    "slotSeconds", "wallSeconds", "userCpu", "sysCpu", "memoryUsed", "diskUsed", "cpusRequested",
)
_USER_DAY_SQL = (
    "SELECT Owner, COUNT(*), "
    f"COUNT(*) FILTER (WHERE JobStatus == {REMOVED_STATUS}), "
    "COUNT(*) FILTER (WHERE NumHolds > 0), "
    "COUNT(*) FILTER (WHERE ExitCode != 0), "
    "COUNT(*) FILTER (WHERE NumJobStarts > 1), "
    "SUM(CumulativeSlotTime), SUM(RemoteWallClockTime), SUM(RemoteUserCpu), SUM(RemoteSysCpu), "
    "SUM(ResidentSetSize), SUM(DiskUsage), SUM(RequestCpus) "
    + _USER_DAY_WHERE
)

# The two requests that can fail, each with the used figure it is compared with.
# An owner missing from one of these lost that sum to an expression; that day's
# requested AND used figures for the resource are both left out, so the
# percentage still compares one set of jobs with itself.
_USER_DAY_REQUESTS = {
    "memoryRequested": ("memoryUsed", f"SELECT Owner, SUM(RequestMemory) {_USER_DAY_WHERE}"),
    "diskRequested": ("diskUsed", f"SELECT Owner, SUM(RequestDisk) {_USER_DAY_WHERE}"),
}

KIB_PER_MB = 1024


def _empty_totals() -> dict[str, float]:
    totals: dict[str, float] = {"jobs": 0}
    for name in _DAY_COUNTS + _DAY_SUMS:
        totals[name] = 0
    return totals


def _merge_totals(running: dict[str, float], day: dict[str, float]) -> None:
    """Fold one day's figures into a running total, in place."""
    running["jobs"] += day["jobs"]
    for name in _DAY_COUNTS + _DAY_SUMS:
        running[name] += day[name]


async def fetch_user_day(day: date) -> dict:
    """One day's per-user totals, keyed by owner.

    Returns the folded numbers rather than raw rows so the cache holds something
    small and already shaped, and so a cache hit costs nothing to reuse.

    A row with no Owner is htcondordb failing to aggregate some value for the
    owners merged into it (see _USER_DAY_WHERE). In the main query its jobs are
    counted as dropped, which marks the range truncated, rather than shown as a
    user named "None"; in a request query it costs only that resource.
    """
    start_sec = _midnight(day)
    params = [start_sec, start_sec, _midnight(day + timedelta(days=1))]
    rows, *request_rows = await asyncio.gather(
        db_query(_USER_DAY_SQL, params),
        *(db_query(sql, params) for _, sql in _USER_DAY_REQUESTS.values()),
    )

    owners: dict[str, dict[str, float]] = {}
    dropped = 0
    for owner, jobs, *values in rows:
        if owner is None:
            dropped += jobs or 0
            continue
        totals = _empty_totals()
        totals["jobs"] = jobs or 0
        for name, value in zip(_USER_DAY_FIELDS, values):
            totals[name] = _as_seconds(value) or 0
        totals["memoryUsed"] /= KIB_PER_MB
        owners[str(group_key(owner))] = totals

    for (requested, (used, _)), result in zip(_USER_DAY_REQUESTS.items(), request_rows):
        sums = {str(group_key(owner)): _as_seconds(total) or 0 for owner, total in result if owner is not None}
        unknown = []
        for owner, totals in owners.items():
            if owner in sums:
                totals[requested] = sums[owner]
            else:
                totals[used] = 0
                unknown.append(owner)
        if unknown:
            logger.warning(
                "User day %s: %s could not be summed for %s; their %s is left out of that day",
                day, requested, ", ".join(sorted(unknown)), used,
            )

    if dropped:
        logger.warning("User day %s: %d jobs came back with no Owner and were left out", day, dropped)
    logger.info("User day %s: %d owners", day, len(owners))
    return {"owners": owners, "dropped": dropped}


def _ratio(numerator: float, denominator: float) -> Optional[float]:
    """A percentage, or None when there is nothing to divide by.

    None rather than zero: an owner with no slot time recorded has unknown CPU
    efficiency, and printing 0% would state the opposite of that.
    """
    if not denominator:
        return None
    return 100.0 * numerator / denominator


# HTCondor records RequestMemory/MemoryUsage in MB and RequestDisk/DiskUsage in
# KiB. Both are reported in GB: summed over a month of jobs, the native units run
# to ten or eleven digits, which no reader can compare at a glance.
KIB_PER_GB = 1024 * 1024
MB_PER_GB = 1024


def _gb(kib: Optional[float]) -> Optional[float]:
    return None if kib is None else kib / KIB_PER_GB


def _user_row(owner: str, totals: dict[str, Any]) -> dict:
    jobs = totals["jobs"]
    slot_seconds = totals["slotSeconds"]
    return {
        "owner": owner,
        "jobs": int(jobs),
        "coreHours": slot_seconds / 3600.0,
        "removed": int(totals["removed"]),
        "removedPct": _ratio(totals["removed"], jobs) or 0.0,
        "held": int(totals["held"]),
        "failed": int(totals["failed"]),
        "failedPct": _ratio(totals["failed"], jobs) or 0.0,
        "retried": int(totals["retried"]),
        "retriedPct": _ratio(totals["retried"], jobs) or 0.0,
        "avgRuntimeSeconds": (totals["wallSeconds"] / jobs) if jobs else None,
        # Requested against used, which is the whole point of these: the gap
        # between the two totals is over-requesting, and the ratio is that gap
        # said as one number.
        #
        # Both totals are in GB, converted from the units HTCondor records --
        # memory in MB, disk in KiB. They are sums over every job in the range,
        # so they are GB summed across jobs rather than GB held at any one moment.
        "memoryRequestedGb": totals["memoryRequested"] / MB_PER_GB,
        "memoryUsedGb": totals["memoryUsed"] / MB_PER_GB,
        "memoryPct": _ratio(totals["memoryUsed"], totals["memoryRequested"]),
        "diskRequestedGb": _gb(totals["diskRequested"]),
        "diskUsedGb": _gb(totals["diskUsed"]),
        "diskPct": _ratio(totals["diskUsed"], totals["diskRequested"]),
        # Cores summed over jobs. Not core-hours -- that is the coreHours column,
        # which weights each job by how long it held them.
        "cpusRequested": totals["cpusRequested"],
    }


async def build_user_range_summary(start: str, end: str) -> dict:
    """Every user who finished a job in the range, busiest first.

    The days are fetched concurrently and cached one by one, so two ranges that
    overlap -- which is nearly every pair a reader looks at in succession -- share
    everything but the days that differ between them.

    Every figure is a count or a sum, each of which merges across days exactly.
    That is a deliberate constraint rather than a coincidence: a median used
    memory was measured and dropped because it cannot be merged this way, and
    asking for it range-wide cost more than the rest of the table put together.

    The fan-out is bounded rather than unbounded: a long range would otherwise
    open hundreds of concurrent queries at once, which costs htcondordb more than
    it costs this process.
    """
    first, last = parse_range(start, end)
    days = range_days(first, last)

    limit = asyncio.Semaphore(DAY_FETCH_CONCURRENCY)

    async def one(day: date) -> dict:
        async with limit:
            return await cached_day(
                ("user-day", day.isoformat()),
                day_cache_ttl(day),
                lambda: fetch_user_day(day),
            )

    results = await asyncio.gather(*(one(day) for day in days))

    merged: dict[str, dict[str, Any]] = {}
    truncated = False
    for result in results:
        truncated = truncated or bool(result["dropped"])
        for owner, totals in result["owners"].items():
            _merge_totals(merged.setdefault(owner, _empty_totals()), totals)

    rows = [_user_row(owner, totals) for owner, totals in merged.items()]
    rows.sort(key=lambda row: (-row["jobs"], row["owner"]))

    return {
        "start": first.isoformat(),
        "end": last.isoformat(),
        "days": len(days),
        "timezone": TIMEZONE,
        "generatedAt": datetime.now(TZ).isoformat(),
        "users": rows,
        "totalUsers": len(rows),
        "truncated": truncated,
        "source": {"host": HTCONDORDB_ADDRESS, "index": HISTORY_TABLE},
    }
