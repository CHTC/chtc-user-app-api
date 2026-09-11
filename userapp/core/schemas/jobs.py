"""Response shapes for the job-history endpoints (userapp/api/routes/jobs).

Field names here are camelCase, unlike the rest of this package. They are a wire
contract with the job viewer, which reads these payloads with the same types it
used when they were baked to disk as stacked-bars.json and day-cards.json, so
renaming a field breaks the page rather than merely restyling it.

Two payloads, because they answer two different questions:

  JobSeries      per-cluster counts of placements and terminal transitions,
                 binned at a fixed interval across the window. A histogram.
  JobDaySummary  per-(cluster, queue-day) cohort censuses, per-day transition
                 counts, the Sankey edge weights, and the end-of-day carry-over
                 census. A cohort retention matrix, not a histogram.
"""

from typing import Optional

from pydantic import Field

from userapp.core.schemas.general import BaseModel


class BatchInfo(BaseModel):
    """A JobBatchName group. One batch usually spans several clusters, so only the
    membership is published and the viewer sums whole clusters to build a batch -
    a job belongs to exactly one cluster, so those sums stay exact."""

    id: str
    name: str
    total: int
    clusters: list[int]


class AdstashSource(BaseModel):
    host: str
    index: str


class AdstashDaySource(AdstashSource):
    terminalRecords: int


class CondorQSource(BaseModel):
    """What the live-queue half of the answer cost, and whether it was complete.

    `schedd` is a comma-joined summary kept for the viewer's existing type; the
    per-node detail is in `schedds`. A non-empty `errors` means the live queue was
    only partly reachable and the payload understates jobs that have not yet
    reached a terminal state."""

    pool: str
    schedd: str
    schedds: list[str] = Field(default_factory=list)
    liveAds: int
    errors: list[str] = Field(default_factory=list)


class CondorQDaySource(CondorQSource):
    stillQueued: int


class ClusterSeries(BaseModel):
    """One cluster's window-long series. Bins are sparse [binIndex, count] pairs,
    bin indices ascending."""

    cluster: int
    batch: str
    total: int
    openingActive: int
    placed: list[tuple[int, int]]
    completed: list[tuple[int, int]]
    removed: list[tuple[int, int]]


class JobSeriesSources(BaseModel):
    adstash: AdstashSource
    condorQ: CondorQSource


class JobSeries(BaseModel):
    owner: str
    anonymized: bool = False
    generatedAt: str
    timezone: str
    days: list[str]
    binHours: int
    binsPerDay: int
    series: list[ClusterSeries]
    batches: list[BatchInfo]
    sources: JobSeriesSources


class ClusterInfo(BaseModel):
    id: int
    total: int
    firstQueued: Optional[str] = Field(default=None)
    batch: str


class Cohort(BaseModel):
    """The jobs one cluster placed on one day, and what became of them.

    `asOf` maps a day key to the four-state breakdown [queued, running,
    completed, removed] at the end of that day, for days from the cohort's own
    queue day forward.

    `day` may precede the window: a cohort placed before it opened, and still
    partly open when it did, is reported under its real placement day with
    `asOf` covering the window's days. Such a row counts only the jobs still open
    at the window's start -- the window that contains the placement day has the
    whole cohort -- which is what lets a viewer stitch consecutive windows into
    one calendar."""

    cluster: int
    day: str
    queued: int
    asOf: dict[str, tuple[int, int, int, int]]


class DayFlows(BaseModel):
    """Sankey edge weights for one cluster-day, in the order the viewer expects."""

    placedTodayToActive: int
    placedBeforeToActive: int
    activeToCompleted: int
    activeToRemoved: int
    placedTodayToRemoved: int
    placedBeforeToRemoved: int
    placedTodayToCompleted: int
    placedBeforeToCompleted: int


class ActivityRow(BaseModel):
    """Transitions on one day, whatever day the jobs were placed.

    `changed` counts distinct jobs that moved; started/completed/removed count
    transitions, so a job that started and finished the same day appears on two
    lines but in `changed` once. Both are reported because the calendar wants the
    first and the day detail wants the second."""

    cluster: int
    day: str
    started: int
    completed: int
    removed: int
    changed: int
    flows: DayFlows


class CarryRow(BaseModel):
    """Non-terminal jobs held at the end of one day. `day` is the sentinel
    "window-start" for the census taken at the instant the window opened."""

    cluster: int
    day: str
    placed: int
    active: int


class JobDaySummarySources(BaseModel):
    adstash: AdstashDaySource
    condorQ: CondorQDaySource


class JobDaySummary(BaseModel):
    owner: str
    anonymized: bool = False
    generatedAt: str
    timezone: str
    days: list[str]
    states: list[str]
    clusters: list[ClusterInfo]
    batches: list[BatchInfo]
    cohorts: list[Cohort]
    activity: list[ActivityRow]
    carry: list[CarryRow]
    sources: JobDaySummarySources
    # Jobs placed inside the window. Adds up across tiled windows, since a job
    # is placed on exactly one day.
    counted: int
    # Jobs placed before the window that were still open when it started. Not
    # additive across windows: the same long-lived job is here in every window
    # it outlives.
    placedBeforeWindow: int


class UserRangeRow(BaseModel):
    """One user's totals over the requested range.

    Every figure is a sum or a count, so the per-day partials add up exactly. The
    three ratios are computed from summed numerators and denominators rather than
    averaged across days, which would weight a quiet day like a busy one.

    The nullable ones have no denominator to divide by -- no slot time recorded,
    nothing requested, no jobs -- and are null rather than zero, because zero
    reads as "perfectly inefficient" when the truth is "not known"."""

    owner: str
    jobs: int
    coreHours: float
    removed: int
    removedPct: float
    held: int
    failed: int
    failedPct: float
    retried: int
    retriedPct: float
    avgRuntimeSeconds: Optional[float] = Field(default=None)

    # Requested against used. The gap between the two totals is the over-request
    # story: a user who asked the pool for 6,000 GB of memory and touched 60 of
    # it was holding a hundred times what they needed.
    #
    # Totals rather than per-job typical values, because a sum merges across days
    # exactly; see the note in _util on why the table is built only from figures
    # that do. Each percentage is one total over the other, so a busy day weighs
    # more than a quiet one, which is what makes it a fair summary of the range.
    #
    # Both resources are reported in GB, converted from what HTCondor records
    # (memory in MB, disk in KiB). They are GB summed over jobs, not GB held at
    # any single moment.
    memoryRequestedGb: float
    memoryUsedGb: float
    memoryPct: Optional[float] = Field(default=None)
    diskRequestedGb: float
    diskUsedGb: float
    diskPct: Optional[float] = Field(default=None)
    # Cores summed over jobs. Distinct from coreHours above, which weights each
    # job by how long it held them.
    cpusRequested: float


class UserRangeSummary(BaseModel):
    """Every user who finished a job in the range, busiest first.

    `end` is exclusive, so consecutive ranges tile without counting the day they
    meet twice."""

    start: str
    end: str
    days: int
    timezone: str
    generatedAt: str
    users: list[UserRangeRow]
    totalUsers: int
    # True when more distinct owners existed than the terms aggregation returned,
    # so the table is a prefix of the real answer rather than all of it.
    truncated: bool = False
    source: AdstashSource
