"""Everything behind the /jobs history endpoints.

Ported from the two bake scripts that fed the job viewer when its data was static
(build-stacked-bar-data.mjs and build-day-data.mjs). The arithmetic is the same;
what changed is where the numbers come from and who is allowed to see them:

  * The Owner filter is the caller's netid rather than an environment variable.
    An admin may ask for someone else's netid; nobody else can.
  * Anonymization is gone. It existed so a public site could publish one user's
    jobs; here a user is looking at their own, so real ClusterIds and real batch
    names are exactly what they need. That also removes the two label stores.
  * condor_q fans out over the submit nodes the owner actually has access to,
    instead of one hardcoded schedd.
  * Day boundaries are DST-correct (see the note on bucketing below).

Neither source is enough alone. Adstash/Elasticsearch holds one terminal record
per job (Completed or Removed) and knows nothing about jobs still in the queue;
condor_q holds the live queue and knows nothing about jobs that already finished.
A cluster in flight appears in both, split across them, so the two are merged and
the terminal record wins.

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
The bakes bucketed with a plain Elasticsearch histogram over a fixed 86400s
interval plus an offset, and refused to run at all when the window straddled a
DST transition, because fixed intervals cannot line up with local midnight on a
23- or 25-hour day. A bake can decline to run; a live endpoint cannot -- a
rolling 35-day window contains the transition for 35 consecutive days, so that
rule would break the page for over a month, twice a year.

So the histograms here are date_histograms carrying an explicit `time_zone`,
which Elasticsearch aligns to real local days, and every bucket key is resolved
against boundaries this module computes in the same zone. The one residue is
that a sub-day bin spanning a DST transition is an hour short or long; that bin
is still assigned to the day it starts in, which is what the viewer draws.
"""

import asyncio
import logging
import os
from array import array
from bisect import bisect_right
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from time import monotonic
from typing import Any, Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from userapp.api.util.htcondor_cli import condor_q, cq_quote
from userapp.core.models.tables import User
from userapp.core.models.views import UserSubmitView

logger = logging.getLogger(__name__)

# --- Configuration ------------------------------------------------------------

# Adstash. The restash-* rollovers are included by the default index pattern;
# their overlap with the primaries is negligible.
ES_HOST = os.environ.get("ES_HOST", "https://elastic-adstash.osg.chtc.io/q")
ES_INDEX = os.environ.get("ES_INDEX", "adstash-chtc-ap-job-history-*")
ES_USERNAME = os.environ.get("ES_USERNAME", "")
ES_PASSWORD = os.environ.get("ES_PASSWORD", "")
ES_TIMEOUT = float(os.environ.get("ES_TIMEOUT", "60"))

CONDOR_POOL = os.environ.get("CONDOR_POOL", "cm.chtc.wisc.edu")

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

# Upper bound on distinct clusters in a window. Exceeding it is an error rather
# than a silent trim, so a truncated answer never reads as a complete one.
CLUSTER_LIMIT = 1000

# The live queue is read once per owner and shared by every window that owner is
# asked about, so it reaches back far enough to serve any window the endpoints
# accept: a job submitted a year before the oldest allowed start and still idle
# is in play throughout. condor_q always applies a QDate window of its own, so
# this is that window's lower edge, counted back from now.
LIVE_LOOKBACK_DAYS = 365
LIVE_QUERY_LOOKBACK_DAYS = LIVE_LOOKBACK_DAYS + 366
LIVE_LIMIT = 500_000
LIVE_TIMEOUT = float(os.environ.get("CONDOR_Q_TIMEOUT", "180"))

# Every attribute either endpoint reads off a live ad. One list rather than one
# per endpoint, so the two can share a single condor_q answer.
LIVE_ATTRS = [
    "ClusterId", "QDate", "JobStatus", "JobStartDate", "EnteredCurrentStatus",
    "NumJobStarts",
    # What the supersede check matches on: aggregations give no per-job keys,
    # so overlap with a terminal record has to be resolved against these.
    "GlobalJobId",
    # A cluster still entirely in the queue has no terminal record at all, so
    # this is the only place its batch name can come from.
    "JobBatchName",
]

# These aggregations cost seconds of Elasticsearch time and up to minutes of
# schedd time, and a page refresh asks for the identical window, so an answer is
# reused briefly. Set to 0 to disable.
CACHE_SECONDS = float(os.environ.get("JOB_HISTORY_CACHE_SECONDS", "60"))
CACHE_MAX_ENTRIES = 64

# The user table is assembled one day at a time rather than as a single query
# over the whole range. A month-wide terms aggregation over Owner costs about six
# seconds against CHTC history; the same month issued a day at a time, merged
# here, costs under three, because the work overlaps and no single search has to
# scan the whole range. Days also tile an arbitrary range exactly, which whole
# weeks cannot, and no individual request comes close to ES_TIMEOUT.
#
# The decomposition only holds because every figure in the table is a sum or a
# count, which merge across days exactly. It is the reason there is no median
# runtime and no distinct-cluster count here: percentiles and cardinality cannot
# be added up from partials, and computing them range-wide would cost more than
# the rest of the table put together.
#
# A day that has ended is settled: Adstash may still receive a straggler, but not
# enough to be worth re-reading every minute. Ranges overlap constantly, so a
# cached day is reused by nearly every subsequent range a reader asks for.
DAY_CACHE_SECONDS_PAST = float(os.environ.get("JOB_DAY_CACHE_SECONDS", "21600"))

# A long range would otherwise open one search per day all at once, which costs
# Elasticsearch more than it costs this process.
DAY_FETCH_CONCURRENCY = int(os.environ.get("JOB_DAY_CONCURRENCY", "12"))

# Distinct owners a single day may report. CHTC runs a few hundred in a busy
# month, so this is headroom rather than a limit anyone should meet; exceeding it
# is reported to the reader rather than silently trimming the table.
USER_TERMS_LIMIT = 2000

# Longest range that may be asked for. A year of days still answers, but slowly
# enough that it is worth making the caller opt into it a quarter at a time.
MAX_RANGE_DAYS = 366

# Terminal state buckets. Hold is deliberately not one of them: the history
# records carry no NumHolds/LastHoldTime, so a hold count would be a fabrication.
# Live ads in JobStatus 5 (Held) fold into Queued, and that is logged when it
# happens.
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
# every job on the page. Elasticsearch needs a concrete value to bucket them
# under, and it has to be one no real batch name would collide with.
NO_BATCH = "__no_batch__"


# --- Calendar -----------------------------------------------------------------


def _midnight(day: date) -> int:
    """Epoch seconds of local midnight starting `day`, DST included."""
    return int(datetime.combine(day, time.min, tzinfo=TZ).timestamp())


class Calendar:
    """The window, its day grid, and its sub-day bin grid, all in local time.

    Boundaries are built from calendar dates rather than by adding 86400 to the
    previous one, so a 23- or 25-hour day is the length it really was. Bucket
    keys and raw timestamps are both resolved against these boundaries by binary
    search, which stays correct whatever Elasticsearch did with its own bucket
    alignment.
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

        # Bucket key that `"missing": 0` lands in: whichever local day contained
        # the epoch. Both an absent field and a present-but-zero timestamp end up
        # there (removed jobs carry CompletionDate 0), so it reads as "no such
        # transition" rather than as a timestamp outside the window.
        self.missing_day_key_ms = _midnight(datetime.fromtimestamp(0, TZ).date()) * 1000

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

    def day_index_from_key(self, key_ms: Any) -> int:
        """Histogram bucket key (epoch millis) -> day index, or -1."""
        if key_ms is None:
            return -1
        return self.day_index(float(key_ms) / 1000)

    def day_index_from_key_clamped(self, key_ms: Any) -> int:
        """Histogram bucket key (epoch millis) -> day_index_clamped."""
        if key_ms is None:
            return -1
        return self.day_index_clamped(float(key_ms) / 1000)

    def day_key(self, seconds: Any) -> Optional[str]:
        """The local calendar date of a timestamp as "YYYY-MM-DD", inside the
        window or not. None for junk, and for the zero that means "no such
        timestamp" -- which is also where the histograms' `missing: 0` lands."""
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return datetime.fromtimestamp(value, TZ).date().isoformat()

    def day_key_from_key(self, key_ms: Any) -> Optional[str]:
        """Histogram bucket key (epoch millis) -> day_key. The missing bucket's
        key is local midnight of the epoch's day, which is before the epoch in
        any zone west of Greenwich and so reads as None here too."""
        if key_ms is None:
            return None
        return self.day_key(float(key_ms) / 1000)

    def bin_index_from_key(self, key_ms: Any) -> int:
        """Histogram bucket key (epoch millis) -> bin index, or -1."""
        if key_ms is None:
            return -1
        return self.bin_index(float(key_ms) / 1000)

    def has_timestamp(self, key_ms: Any) -> bool:
        """Whether a bucket represents a real timestamp at all.

        The Sankey needs this and the day index cannot answer it: a job that
        started before the window ran, and flows out of Active, while one that
        never started flows straight from Placed -- both give a day index of -1.
        """
        if key_ms is None:
            return False
        return float(key_ms) != float(self.missing_day_key_ms)


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


# --- Elasticsearch ------------------------------------------------------------


def _es_client() -> httpx.AsyncClient:
    auth = httpx.BasicAuth(ES_USERNAME, ES_PASSWORD) if ES_USERNAME else None
    return httpx.AsyncClient(base_url=ES_HOST, auth=auth, timeout=ES_TIMEOUT)


async def es_search(client: httpx.AsyncClient, body: dict, attempts: int = 4) -> dict:
    """POST one search and return the decoded body.

    Only transport failures retry. A 4xx/5xx from Elasticsearch is a real problem
    -- a bad query, a missing index, expired credentials -- and repeating it just
    delays the error.
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            response = await client.post(f"/{ES_INDEX}/_search", json=body, params={"size": 0})
        except httpx.TransportError as error:
            last_error = error
            if attempt == attempts:
                break
            backoff = 0.5 * 2 ** (attempt - 1)
            logger.warning(
                "Elasticsearch transport error (attempt %d/%d): %s; retrying in %.1fs",
                attempt, attempts, error, backoff,
            )
            await asyncio.sleep(backoff)
            continue

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Elasticsearch search failed: {response.status_code} {response.text[:500]}",
            )
        return response.json()

    raise HTTPException(status_code=502, detail=f"Elasticsearch unreachable: {last_error}")


def _in_window(field: str, calendar: Calendar) -> dict:
    """`format` is required: without it Elasticsearch reads bare numbers in a range
    over a date field as epoch MILLIS whatever the field's own format says, and
    the window silently matches nothing."""
    return {
        "range": {
            field: {"gte": calendar.start_sec, "lt": calendar.end_sec, "format": "epoch_second"}
        }
    }


def _day_histogram(field: str, sub: Optional[dict] = None) -> dict:
    """Local-day histogram over an epoch-seconds field.

    `missing: 0` funnels an absent value into the same bucket a present-but-zero
    timestamp already lands in, so both read back as "no such transition".
    """
    agg: dict[str, Any] = {
        "date_histogram": {
            "field": field,
            "calendar_interval": "1d",
            "time_zone": TIMEZONE,
            "min_doc_count": 1,
            "missing": 0,
        }
    }
    if sub:
        agg["aggs"] = sub
    return agg


def _bin_histogram(field: str, calendar: Calendar) -> dict:
    """Sub-day histogram at the calendar's bin width, aligned to local time."""
    return {
        "date_histogram": {
            "field": field,
            "fixed_interval": f"{calendar.bin_hours}h",
            "time_zone": TIMEZONE,
            "min_doc_count": 1,
            "missing": 0,
        }
    }


def _cluster_buckets(response: dict) -> list[dict]:
    """The cluster buckets, refusing a silently truncated answer."""
    aggregations = response.get("aggregations") or {}
    cluster = aggregations.get("cluster") or {}
    dropped = cluster.get("sum_other_doc_count", 0)
    if dropped:
        raise HTTPException(
            status_code=507,
            detail=(
                f"This window covers more than {CLUSTER_LIMIT} clusters "
                f"({dropped} more documents did not fit); ask for a shorter window."
            ),
        )
    return cluster.get("buckets", [])


def _matched(response: dict) -> int:
    total = ((response.get("hits") or {}).get("total")) or 0
    return total.get("value", 0) if isinstance(total, dict) else int(total)


async def fetch_bin_buckets(client: httpx.AsyncClient, owner: str, calendar: Calendar) -> list[dict]:
    """Per cluster: jobs placed per bin, and terminal ends per bin split by status.

    The union filter matters -- a job placed before the window that ended inside
    it must still contribute its end. Ends come from EnteredCurrentStatus for
    both terminal statuses: for a terminal record the current status IS the
    terminal one, and unlike CompletionDate it is also set on Removed records.
    """
    body = {
        "size": 0,
        # Without this the reported total silently caps at 10000, which reads as
        # if the aggregation only saw 10000 jobs.
        "track_total_hits": True,
        "query": {
            "bool": {
                # adstash maps these as bare keyword fields, not text with a
                # .keyword subfield.
                "filter": [{"term": {"Owner": owner}}],
                "should": [_in_window("QDate", calendar), _in_window("EnteredCurrentStatus", calendar)],
                "minimum_should_match": 1,
            }
        },
        "aggs": {
            "cluster": {
                "terms": {"field": "ClusterId", "size": CLUSTER_LIMIT},
                "aggs": {
                    # size 2 rather than 1 so a cluster whose jobs disagree about
                    # their batch name is detected instead of silently filed
                    # under whichever name won. See resolve_cluster_batches.
                    "batch": {"terms": {"field": "JobBatchName", "size": 2, "missing": NO_BATCH}},
                    "placed": _bin_histogram("QDate", calendar),
                    "status": {
                        "terms": {"field": "Status", "size": 20, "missing": "Unknown"},
                        "aggs": {"ends": _bin_histogram("EnteredCurrentStatus", calendar)},
                    },
                },
            }
        },
    }
    response = await es_search(client, body)
    logger.info("Adstash matched %d records in %sms", _matched(response), response.get("took"))
    return _cluster_buckets(response)


async def fetch_opening_active(client: httpx.AsyncClient, owner: str, calendar: Calendar) -> dict[int, int]:
    """Terminal records that were in play when the window opened: placed before
    it, ended inside or after it. Records with no usable end are excluded --
    their timeline is unknowable."""
    body = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"Owner": owner}},
                    {"range": {"QDate": {"lt": calendar.start_sec, "format": "epoch_second"}}},
                    {"range": {"EnteredCurrentStatus": {"gte": calendar.start_sec, "format": "epoch_second"}}},
                ]
            }
        },
        "aggs": {"cluster": {"terms": {"field": "ClusterId", "size": CLUSTER_LIMIT}}},
    }
    response = await es_search(client, body)
    return {int(bucket["key"]): bucket["doc_count"] for bucket in _cluster_buckets(response)}


def overlap_query(owner: str, calendar: Calendar) -> dict:
    """Every terminal record of `owner` whose job was open at some point inside
    the window: placed before the window closed, and finished on or after it
    opened.

    That is the selection that makes windows tile (see the module note). It
    contains everything the old "had a transition inside the window" filter
    did -- a placement or an end inside the window both imply overlap -- and adds
    the jobs that were placed before the window and finished after it, which are
    exactly the ones a past window was missing from its end-of-day census.

    A record with no usable end is kept only if it was placed inside the window:
    its timeline is unknowable, so it counts as a placement and nothing more,
    which is what the old filter did with it too.
    """
    return {
        "bool": {
            # adstash maps these as bare keyword fields, not text with a .keyword
            # subfield.
            "filter": [
                {"term": {"Owner": owner}},
                {"range": {"QDate": {"lt": calendar.end_sec, "format": "epoch_second"}}},
            ],
            "should": [
                {"range": {"EnteredCurrentStatus": {"gte": calendar.start_sec, "format": "epoch_second"}}},
                {"range": {"QDate": {"gte": calendar.start_sec, "format": "epoch_second"}}},
            ],
            "minimum_should_match": 1,
        }
    }


async def fetch_day_buckets(client: httpx.AsyncClient, owner: str, calendar: Calendar) -> list[dict]:
    """The whole window as one nested aggregation.

    Everything the day summary reports is a group-by, so it is computed
    server-side rather than by streaming documents. The shape is the joint
    distribution of (cluster, status, queue day, start day, end day); state as of
    any day D follows arithmetically from that: terminal if endDay <= D, else
    running if startDay <= D, else queued.

    The selection is every job open at some point in the window (overlap_query).
    A job placed inside it gets a cohort of its own; a job placed before it gets a
    cohort keyed by its real placement day, covering only the window's days; and
    both contribute to the transition counts and the end-of-day census on the
    days they were here.
    """
    body = {
        "size": 0,
        "track_total_hits": True,
        "query": overlap_query(owner, calendar),
        "aggs": {
            "cluster": {
                "terms": {"field": "ClusterId", "size": CLUSTER_LIMIT},
                "aggs": {
                    "batch": {"terms": {"field": "JobBatchName", "size": 2, "missing": NO_BATCH}},
                    "status": {
                        "terms": {"field": "Status", "size": 20, "missing": "Unknown"},
                        "aggs": {
                            "queueDay": _day_histogram(
                                "QDate",
                                {
                                    "startDay": _day_histogram(
                                        "JobStartDate",
                                        {
                                            # Removed jobs always carry
                                            # CompletionDate 0, so their end time
                                            # is EnteredCurrentStatus. Which one
                                            # is real is decided by the enclosing
                                            # status bucket; both are collected
                                            # because a histogram cannot switch
                                            # fields conditionally.
                                            "endCompleted": _day_histogram("CompletionDate"),
                                            "endRemoved": _day_histogram("EnteredCurrentStatus"),
                                        },
                                    )
                                },
                            )
                        },
                    },
                },
            }
        },
    }
    response = await es_search(client, body)
    logger.info("Adstash matched %d records in %sms", _matched(response), response.get("took"))
    return _cluster_buckets(response)


async def drop_superseded_ads(client: httpx.AsyncClient, live_ads: dict[str, dict]) -> int:
    """Remove live ads that already have a terminal record, in place.

    A job finishing between the two queries would otherwise be counted twice --
    once as queued, once as completed. Aggregations give counts, not job keys, so
    the overlap cannot be spotted while folding buckets; instead the (small) set
    of live ads is checked directly by GlobalJobId. Ads without one are left
    alone: a duplicate is a better failure than a silently dropped job.
    """
    if not live_ads:
        return 0

    by_global_id: dict[str, str] = {}
    for key, ad in live_ads.items():
        if ad.get("GlobalJobId"):
            by_global_id[str(ad["GlobalJobId"])] = key
    if not by_global_id:
        logger.warning("Live ads carry no GlobalJobId; skipping the supersede check.")
        return 0

    ids = list(by_global_id)
    chunk_size = 1000  # the terms-query ceiling is 65536; stay well clear
    dropped = 0
    for start in range(0, len(ids), chunk_size):
        chunk = ids[start:start + chunk_size]
        response = await es_search(
            client,
            {"size": len(chunk), "_source": ["GlobalJobId"], "query": {"terms": {"GlobalJobId": chunk}}},
        )
        for hit in ((response.get("hits") or {}).get("hits") or []):
            found = (hit.get("_source") or {}).get("GlobalJobId")
            key = by_global_id.get(str(found)) if found else None
            if key is not None and live_ads.pop(key, None) is not None:
                dropped += 1
    return dropped


# --- Live queue ---------------------------------------------------------------


async def owner_schedds(session, user_id: int) -> list[str]:
    """Schedds to ask about this owner: the submit nodes their group membership
    grants them.

    Only names that look like hostnames are usable as a `condor_q -name`; the
    table also holds entries such as "htc_transfer" that name a service rather
    than a schedd, and asking for those would just fail.
    """
    rows = (await session.execute(
        select(UserSubmitView.name).where(UserSubmitView.user_id == user_id)
    )).scalars().all()
    return sorted({name for name in rows if name and "." in name})


async def query_live_ads(schedds: list[str], owner: str) -> tuple[dict[str, dict], list[str]]:
    """Query every schedd for this owner's live ads, keyed "<schedd>:<cluster>.<proc>".

    Keys are qualified by schedd because condor_q's own keys are unique only
    within one schedd: two of them can each hold cluster 12 proc 0.

    A schedd that fails is reported rather than fatal. The live queue is the only
    source for jobs that have not reached a terminal state, so losing one means
    an understatement, not a wrong answer -- and an understated page beats no
    page at all when a single AP is down or off VPN.

    Not window-specific: this asks for everything the owner has in the queue back
    to LIVE_QUERY_LOOKBACK_DAYS, and the caller narrows it to a window with
    live_ads_in_window. The queue is the same queue whichever week is being
    looked at, and it is the slow leg of every request, so it is read once.
    """
    if not schedds:
        return {}, ["no submit nodes on record for this user; the live queue was not queried"]

    now = datetime.now(TZ)
    live_start = now - timedelta(days=LIVE_QUERY_LOOKBACK_DAYS)
    # A little past now, so an ad queued between building this timestamp and the
    # schedd answering is not cut off by the window's exclusive end.
    live_end = now + timedelta(days=1)

    async def query(schedd: str) -> dict[str, dict]:
        return await condor_q(
            constraint=f"Owner == {cq_quote(owner)}",
            attrs=LIVE_ATTRS,
            start=live_start,
            end=live_end,
            pool=CONDOR_POOL,
            name=schedd,
            # The API service is not the owner, so its own jobs are not the ones
            # being asked about.
            all_users=True,
            limit=LIVE_LIMIT,
            timeout=LIVE_TIMEOUT,
        )

    results = await asyncio.gather(*(query(schedd) for schedd in schedds), return_exceptions=True)

    ads: dict[str, dict] = {}
    errors: list[str] = []
    for schedd, result in zip(schedds, results):
        if isinstance(result, BaseException):
            logger.warning("condor_q against %s failed: %s", schedd, result)
            errors.append(f"{schedd}: {result}")
            continue
        for key, ad in result.items():
            ads[f"{schedd}:{key}"] = ad
    return ads, errors


def live_ads_in_window(ads: dict[str, dict], calendar: Calendar) -> dict[str, dict]:
    """The live ads that were open at some point inside the window.

    A live ad is open now, so it overlaps any window that closes after it was
    placed: the only test is QDate before the window's end. An ad placed after a
    past window closed was not there yet and is left out, which is what keeps a
    past week's census from counting this week's submissions.

    Ads with no readable QDate are kept. Dropping a job for a missing attribute
    would understate the queue, and the aggregators already treat an unknown
    placement as "before the window".
    """
    selected: dict[str, dict] = {}
    for key, ad in ads.items():
        queued_at = _as_seconds(ad.get("QDate"))
        if queued_at is None or queued_at < calendar.end_sec:
            selected[key] = ad
    return selected


async def fetch_live_ads(
    client: httpx.AsyncClient, schedds: list[str], owner: str, calendar: Calendar
) -> tuple[dict[str, dict], list[str]]:
    """This owner's live ads that overlap the window, with any terminal record
    that supersedes one already removed.

    The condor_q fan-out and the supersede check run once per owner and are held
    for CACHE_SECONDS, then narrowed to the window here. A calendar month asked
    for as five weekly windows costs one read of the queue rather than five --
    and the lock inside the cache means the five arriving together still cost one.
    """
    async def build() -> tuple[dict[str, dict], list[str]]:
        ads, errors = await query_live_ads(schedds, owner)
        superseded = await drop_superseded_ads(client, ads)
        if superseded:
            logger.info("%d live ads superseded by a terminal record", superseded)
        return ads, errors

    ads, errors = await _cached_in(
        _live_cache, _live_cache_locks, ("live", owner, tuple(schedds)),
        CACHE_SECONDS, LIVE_CACHE_MAX_ENTRIES, build,
    )
    return live_ads_in_window(ads, calendar), errors


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


async def resolve_owner(session, requested: Optional[str], user_token, admin: bool) -> tuple[str, int]:
    """The netid whose jobs are being asked about, and that user's id.

    A user may only ask about themselves; an admin may name anyone. The netid is
    what HTCondor records as Owner, which is why it is the join between this
    application's users and the pool's jobs.
    """
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


def _schedd_summary(schedds: list[str]) -> str:
    """One-line description of who was asked, for the prose the viewer prints.

    Never an empty string: the shared schema base coerces "" to None, and the
    viewer reads this field as text.
    """
    return ", ".join(schedds) if schedds else "no submit node on record"


async def build_job_series(
    owner: str, schedds: list[str], days_back: int, bin_hours: int,
    start: Optional[str] = None, end: Optional[str] = None,
) -> dict:
    """Per-cluster placements and terminal transitions, binned across the window.

    Three series per cluster plus an opening census is exactly what a cumulative
    census of any day needs: of every job in play that day (active when it
    opened, plus placed so far), how many are still active, completed, or
    removed. The day slicing, running sums and percentages are the client's.
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

    async with _es_client() as client:
        # Independent of each other, so they run together: the live queue is the
        # slowest leg by far and there is no reason for Adstash to wait on it.
        (live_ads, live_errors), opening, cluster_buckets = await asyncio.gather(
            fetch_live_ads(client, schedds, owner, calendar),
            fetch_opening_active(client, owner, calendar),
            fetch_bin_buckets(client, owner, calendar),
        )

    # 1. Live queue: the only source for jobs with no terminal record yet.
    for ad in live_ads.values():
        cluster = _as_int(ad.get("ClusterId"))
        if cluster is None:
            continue
        note_batch(batch_tally, cluster, ad.get("JobBatchName"), 1)
        entry = series_for(cluster)
        placed_bin = calendar.bin_index(ad.get("QDate"))
        queued_at = _as_seconds(ad.get("QDate"))
        if placed_bin >= 0:
            entry["placed"][placed_bin] += 1
        elif queued_at is not None and queued_at < calendar.start_sec:
            # Placed before the window and still live now: in play throughout.
            entry["openingActive"] += 1

    # 2. Terminal records already in play when the window opened.
    for cluster, count in opening.items():
        series_for(cluster)["openingActive"] += count

    # 3. Terminal records: placements and ends per bin.
    unexpected: set[str] = set()
    for bucket in cluster_buckets:
        cluster = _as_int(bucket["key"])
        if cluster is None:
            continue
        for batch_bucket in (bucket.get("batch") or {}).get("buckets", []):
            note_batch(batch_tally, cluster, batch_bucket["key"], batch_bucket["doc_count"])
        entry = series_for(cluster)
        for placed_bucket in (bucket.get("placed") or {}).get("buckets", []):
            placed_bin = calendar.bin_index_from_key(placed_bucket["key"])
            if placed_bin >= 0:
                entry["placed"][placed_bin] += placed_bucket["doc_count"]
        for status_bucket in (bucket.get("status") or {}).get("buckets", []):
            status = str(status_bucket["key"])
            if status == "Completed":
                target = entry["completed"]
            elif status == "Removed":
                target = entry["removed"]
            else:
                unexpected.add(status)
                continue
            for end_bucket in (status_bucket.get("ends") or {}).get("buckets", []):
                end_bin = calendar.bin_index_from_key(end_bucket["key"])
                if end_bin >= 0:
                    target[end_bin] += end_bucket["doc_count"]
    if unexpected:
        logger.warning("Unexpected terminal statuses ignored: %s", ", ".join(sorted(unexpected)))

    # 4. Publish, largest cluster first so batch membership is built in a
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
        "sources": {
            "adstash": {"host": ES_HOST, "index": ES_INDEX},
            "condorQ": {
                "pool": CONDOR_POOL,
                "schedd": _schedd_summary(schedds),
                "schedds": schedds,
                "liveAds": len(live_ads),
                "errors": live_errors,
            },
        },
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
    owner: str, schedds: list[str], days_back: int,
    start: Optional[str] = None, end: Optional[str] = None,
) -> dict:
    """Per-day cohort censuses, transition counts and flow edges for the window.

    Fully pre-aggregated: for every (cluster, queue-day) cohort this stores the
    four-state breakdown as of the end of every later day, so the client does no
    per-job arithmetic however many jobs the window holds.
    """
    calendar = (
        build_calendar_for_range(start, end, DEFAULT_BIN_HOURS)
        if start and end
        else build_calendar(days_back, DEFAULT_BIN_HOURS)
    )
    aggregator = _DayAggregator(calendar)

    async with _es_client() as client:
        (live_ads, live_errors), cluster_buckets = await asyncio.gather(
            fetch_live_ads(client, schedds, owner, calendar),
            fetch_day_buckets(client, owner, calendar),
        )

    # 1. Terminal records.
    leaf_buckets = 0
    unexpected: set[str] = set()
    for cluster_bucket in cluster_buckets:
        cluster = _as_int(cluster_bucket["key"])
        if cluster is None:
            continue
        for batch_bucket in (cluster_bucket.get("batch") or {}).get("buckets", []):
            note_batch(aggregator.batch_tally, cluster, batch_bucket["key"], batch_bucket["doc_count"])

        for status_bucket in (cluster_bucket.get("status") or {}).get("buckets", []):
            status = str(status_bucket["key"])
            removed = status == "Removed"
            if status not in ("Removed", "Completed"):
                unexpected.add(status)

            for queue_bucket in (status_bucket.get("queueDay") or {}).get("buckets", []):
                queue_day = calendar.day_index_from_key(queue_bucket["key"])
                queue_key = calendar.day_key_from_key(queue_bucket["key"])
                for start_bucket in (queue_bucket.get("startDay") or {}).get("buckets", []):
                    # Clamped: a start after the window closed must read as
                    # "queued throughout", not as "running since before it".
                    start_day = calendar.day_index_from_key_clamped(start_bucket["key"])
                    # Distinguishes "started before the window" from "never
                    # started": both give -1, but only the first occupied Active.
                    ever_ran = calendar.has_timestamp(start_bucket["key"])
                    # Removed jobs carry CompletionDate 0, so their end time
                    # lives in EnteredCurrentStatus; the status bucket decides
                    # which branch is the real one.
                    end_agg = start_bucket.get("endRemoved" if removed else "endCompleted") or {}

                    for end_bucket in end_agg.get("buckets", []):
                        leaf_buckets += 1
                        aggregator.add(
                            cluster,
                            queue_day,
                            queue_key=queue_key,
                            # A job that started before the window was running
                            # from its first day. Left at -1 it would be painted
                            # queued, and a cohort's queued/running split would
                            # disagree between a window and the one before it.
                            run_from_day=0 if ever_ran and start_day < 0 else start_day,
                            started_day=start_day,
                            end_day=calendar.day_index_from_key_clamped(end_bucket["key"]),
                            end_state=STATE_REMOVED if removed else STATE_COMPLETED,
                            count=end_bucket["doc_count"],
                            ever_ran=ever_ran,
                            has_end=calendar.has_timestamp(end_bucket["key"]),
                        )
    logger.info("Folded %d leaf buckets", leaf_buckets)
    if unexpected:
        logger.warning(
            "Statuses treated as completed: %s. Only Completed and Removed are modelled.",
            ", ".join(sorted(unexpected)),
        )

    # 2. Whatever is still only in the queue.
    for ad in live_ads.values():
        cluster = _as_int(ad.get("ClusterId"))
        if cluster is None:
            continue
        status = _as_int(ad.get("JobStatus"))
        if status == 5:
            aggregator.held_live += 1
        started_at = _as_seconds(ad.get("JobStartDate"))
        # Clamped for the same reason as the terminal records: a past window
        # can hold an ad that only started after it closed.
        started_day = calendar.day_index_clamped(started_at)
        note_batch(aggregator.batch_tally, cluster, ad.get("JobBatchName"), 1)
        aggregator.add(
            cluster,
            calendar.day_index(ad.get("QDate")),
            queue_key=calendar.day_key(ad.get("QDate")),
            # Only a Running ad (JobStatus 2) is actually running; Idle and Held
            # both read as Queued. One that started before the window has been
            # running since its first day.
            run_from_day=max(started_day, 0) if status == 2 else -1,
            started_day=started_day,
            end_day=-1,
            # A live ad knows whether it ever ran even when the start fell before
            # the window, which the terminal records cannot say as precisely.
            ever_ran=bool(started_at and started_at > 0),
        )
    if aggregator.held_live:
        logger.warning(
            "%d live ads are Held (JobStatus 5); counted as Queued because the history "
            "records carry no hold data to pair them with.", aggregator.held_live,
        )

    return aggregator.to_payload(
        owner,
        {
            "adstash": {
                "host": ES_HOST,
                "index": ES_INDEX,
                "terminalRecords": aggregator.counted + aggregator.placed_before_window - len(live_ads),
            },
            "condorQ": {
                "pool": CONDOR_POOL,
                "schedd": _schedd_summary(schedds),
                "schedds": schedds,
                "liveAds": len(live_ads),
                "stillQueued": len(live_ads),
                "errors": live_errors,
            },
        },
    )


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
    tile an arbitrary range exactly, which whole weeks cannot, and they are
    cheaper: one day of CHTC history answers in a few hundred milliseconds, so a
    month issued a day at a time and merged costs about a third of what the same
    month costs as one query, and never comes close to ES_TIMEOUT.
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


def _user_day_body(start_sec: int, end_sec: int) -> dict:
    """Every user's totals for one day, in one aggregation.

    Sums and counts only, deliberately. Each of these merges across days by
    addition, which is what lets a range be assembled from its days; a percentile
    or a cardinality would not, and would have to be paid for range-wide.

    `held` tests for the presence of NumHolds rather than for a positive value:
    HTCondor only writes the attribute onto a record that was actually held, so
    the field existing IS the condition, and `exists` is cheaper than a range.
    """
    return {
        "size": 0,
        "track_total_hits": False,
        "query": {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "EnteredCurrentStatus": {
                                "gte": start_sec, "lt": end_sec, "format": "epoch_second",
                            }
                        }
                    }
                ]
            }
        },
        "aggs": {
            "user": {
                "terms": {"field": "Owner", "size": USER_TERMS_LIMIT, "order": {"_count": "desc"}},
                "aggs": {
                    "removed": {"filter": {"term": {"Status": "Removed"}}},
                    "held": {"filter": {"exists": {"field": "NumHolds"}}},
                    "failed": {
                        "filter": {
                            "bool": {
                                "must": [{"exists": {"field": "ExitCode"}}],
                                "must_not": [{"term": {"ExitCode": 0}}],
                            }
                        }
                    },
                    "retried": {"filter": {"range": {"NumJobStarts": {"gt": 1}}}},
                    # Slot time is wall time already multiplied by the cores the
                    # job provisioned, and it is written on every record, so the
                    # core-hours column costs a plain sum instead of a script.
                    "slotSeconds": {"sum": {"field": "CumulativeSlotTime"}},
                    "wallSeconds": {"sum": {"field": "RemoteWallClockTime"}},
                    "userCpu": {"sum": {"field": "RemoteUserCpu"}},
                    "sysCpu": {"sum": {"field": "RemoteSysCpu"}},
                    # Requested against used, for each of the three resources.
                    # Summed rather than averaged per day: the ratio the table
                    # shows is one total over another, so a day on which the user
                    # ran ten jobs cannot weigh as heavily as one on which they
                    # ran ten thousand.
                    #
                    # Memory is in MB and disk in KiB, as HTCondor records them;
                    # both are converted once, in _user_row.
                    "memoryUsed": {"sum": {"field": "MemoryUsage"}},
                    "memoryRequested": {"sum": {"field": "RequestMemory"}},
                    "diskUsed": {"sum": {"field": "DiskUsage"}},
                    "diskRequested": {"sum": {"field": "RequestDisk"}},
                    "cpusRequested": {"sum": {"field": "RequestCpus"}},
                },
            }
        },
    }


# The per-user figures a day contributes. Every one is a count or a sum, both of
# which add across any number of days exactly -- that is what lets a range be
# assembled out of cached days. Anything that cannot be merged this way (a median,
# a percentile, a distinct count) does not belong in this table: it would have to
# be asked for range-wide, which was measured at about six seconds and costs more
# than everything here combined.
_DAY_COUNTS = ("removed", "held", "failed", "retried")
_DAY_SUMS = (
    "slotSeconds", "wallSeconds", "userCpu", "sysCpu",
    "memoryUsed", "memoryRequested", "diskUsed", "diskRequested", "cpusRequested",
)


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


async def fetch_user_day(client: httpx.AsyncClient, day: date) -> dict:
    """One day's per-user totals, keyed by owner.

    Returns the folded numbers rather than raw buckets so the cache holds
    something small and already shaped, and so a cache hit costs nothing to
    reuse.
    """
    body = _user_day_body(_midnight(day), _midnight(day + timedelta(days=1)))
    response = await es_search(client, body)
    aggregation = (response.get("aggregations") or {}).get("user") or {}

    owners: dict[str, dict[str, float]] = {}
    for bucket in aggregation.get("buckets", []):
        totals = _empty_totals()
        totals["jobs"] = bucket.get("doc_count", 0)
        for name in _DAY_COUNTS:
            totals[name] = (bucket.get(name) or {}).get("doc_count", 0)
        for name in _DAY_SUMS:
            totals[name] = (bucket.get(name) or {}).get("value") or 0
        owners[str(bucket["key"])] = totals

    logger.info("Adstash user day %s: %d owners in %sms", day, len(owners), response.get("took"))
    return {"owners": owners, "dropped": aggregation.get("sum_other_doc_count", 0)}


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

    Every figure is a count, a sum or a maximum, each of which merges across days
    exactly. That is a deliberate constraint rather than a coincidence: a median
    used memory was measured and dropped because it cannot be merged this way, and
    asking for it range-wide cost about six seconds on a range nobody had opened
    before -- more than the rest of the table put together.

    The fan-out is bounded rather than unbounded: a long range would otherwise
    open hundreds of concurrent searches at once, which costs Elasticsearch more
    than it costs this process.
    """
    first, last = parse_range(start, end)
    days = range_days(first, last)

    limit = asyncio.Semaphore(DAY_FETCH_CONCURRENCY)

    async with _es_client() as client:

        async def one(day: date) -> dict:
            async with limit:
                return await cached_day(
                    ("user-day", day.isoformat()),
                    day_cache_ttl(day),
                    lambda: fetch_user_day(client, day),
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
        "source": {"host": ES_HOST, "index": ES_INDEX},
    }
