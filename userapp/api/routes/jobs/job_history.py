"""Job history for the job viewer.

Three endpoints, because the viewer asks three different questions and they have
genuinely different shapes:

  GET /jobs/users        one row per user who finished a job in a date range,
                         busiest first. The only endpoint here that is about
                         everybody rather than about one owner.
  GET /jobs/series       a histogram - per cluster, how many jobs were placed,
                         completed and removed in each bin across the window.
                         Window length and bin width are parameters, so this is
                         reusable by anything that wants job counts over time.
  GET /jobs/day-summary  a cohort retention matrix - for every (cluster, queue
                         day) cohort, what became of it by the end of every later
                         day, plus that day's transition counts and the flow
                         edges between states.

The second could in principle be expressed as parameters on the first, but only
by inventing a query language for a shape nothing else asks for, so it stays its
own endpoint rather than a generalisation nobody would reuse.

Access: the whole router is admin-only while the feature is being tested. The
per-owner endpoints are written so a user could later be allowed to see their
own jobs (see resolve_owner), but that door is closed for now by the router
dependency below; opening it means removing check_is_admin from the router and
re-enabling the per-owner tests. HTCondor records the submitter as `Owner`,
which is the netid, so that is the join between this application's users and
the pool's jobs. `owner` names any netid; it defaults to the caller's own.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from userapp.api.routes.jobs._util import (
    ALLOWED_BIN_HOURS,
    DEFAULT_BIN_HOURS,
    DEFAULT_DAYS_BACK,
    MAX_DAYS_BACK,
    build_job_day_summary,
    build_job_series,
    build_user_range_summary,
    cached,
    owner_schedds,
    resolve_owner,
)
from userapp.api.routes.security import (
    check_is_admin,
    check_is_authenticated,
    get_user_from_cookie,
    is_admin,
)
from userapp.core.schemas.jobs import JobDaySummary, JobSeries, UserRangeSummary
from userapp.db import session_generator

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
    # TEMPORARY: every endpoint here is admin-only while the feature is being
    # tested. Authentication is checked first so an anonymous caller gets a 401
    # rather than a 403 that implies they are a known non-admin.
    dependencies=[Depends(check_is_authenticated), Depends(check_is_admin)],
    responses={
        401: {
            "description": "Not authenticated"
        },
        403: {
            "description": "Not an admin; these endpoints are admin-only for now"
        },
        404: {
            "description": "Not found"
        }
    }
)

_OWNER_DESCRIPTION = (
    "Netid whose jobs to report. Defaults to the caller's own netid; required "
    "when authenticating with an API token."
)
_DAYS_BACK_DESCRIPTION = (
    "Days of history, counting back from today. The window is inclusive of both "
    "ends, so the default covers 35 days."
)
_RANGE_DESCRIPTION = (
    "Optional explicit window, as YYYY-MM-DD. Given together they replace "
    "days_back, so the viewer can be pointed at a past range rather than the "
    "days leading up to today. `end` is exclusive, matching /jobs/users, so the "
    "same pair of dates can be passed straight through from the table."
)
_START_DESCRIPTION = "First day to report, as YYYY-MM-DD. Inclusive."
_END_DESCRIPTION = (
    "Day to stop at, as YYYY-MM-DD. Exclusive, so consecutive ranges tile "
    "without counting the day they meet twice."
)


@router.get("/series")
async def get_job_series(
    owner: Optional[str] = Query(default=None, description=_OWNER_DESCRIPTION),
    days_back: int = Query(default=DEFAULT_DAYS_BACK, ge=1, le=MAX_DAYS_BACK, description=_DAYS_BACK_DESCRIPTION),
    start: Optional[str] = Query(default=None, description=_RANGE_DESCRIPTION, examples=["2026-07-01"]),
    end: Optional[str] = Query(default=None, description=_RANGE_DESCRIPTION, examples=["2026-08-01"]),
    bin_hours: int = Query(
        default=DEFAULT_BIN_HOURS,
        description=f"Width of each bin in hours; must divide 24. One of {list(ALLOWED_BIN_HOURS)}.",
    ),
    session=Depends(session_generator),
    user_token=Depends(get_user_from_cookie),
    admin=Depends(is_admin),
) -> JobSeries:
    """Per-cluster placements and terminal transitions, binned across the window.

    Merged from Adstash (one terminal record per finished job) and the live
    condor_q queue (everything that has not finished). Counts are sparse: a bin
    with no jobs is absent rather than zero.
    """
    if bin_hours not in ALLOWED_BIN_HOURS:
        # Checked here rather than only in the aggregation so a bad width never
        # reaches the response cache. Pydantic cannot express it as a Literal:
        # query parameters arrive as strings and would not coerce.
        raise HTTPException(
            status_code=422, detail=f"bin_hours must be one of {list(ALLOWED_BIN_HOURS)}"
        )

    if (start is None) != (end is None):
        raise HTTPException(status_code=422, detail="start and end must be given together")

    netid, user_id = await resolve_owner(session, owner, user_token, admin)
    schedds = await owner_schedds(session, user_id)
    return await cached(
        ("series", netid, days_back, bin_hours, start, end),
        lambda: build_job_series(netid, schedds, days_back, bin_hours, start, end),
    )


@router.get("/day-summary")
async def get_job_day_summary(
    owner: Optional[str] = Query(default=None, description=_OWNER_DESCRIPTION),
    days_back: int = Query(default=DEFAULT_DAYS_BACK, ge=1, le=MAX_DAYS_BACK, description=_DAYS_BACK_DESCRIPTION),
    start: Optional[str] = Query(default=None, description=_RANGE_DESCRIPTION, examples=["2026-07-01"]),
    end: Optional[str] = Query(default=None, description=_RANGE_DESCRIPTION, examples=["2026-08-01"]),
    session=Depends(session_generator),
    user_token=Depends(get_user_from_cookie),
    admin=Depends(is_admin),
) -> JobDaySummary:
    """What became of each day's submissions, day by day.

    For every (cluster, queue day) cohort this reports the four-state breakdown
    as of the end of each later day, alongside the day's own transition counts
    and the flow edges between states. Pre-aggregated, so the response stays a
    few hundred kilobytes whether the window holds a thousand jobs or a million.
    """
    if (start is None) != (end is None):
        raise HTTPException(status_code=422, detail="start and end must be given together")

    netid, user_id = await resolve_owner(session, owner, user_token, admin)
    schedds = await owner_schedds(session, user_id)
    return await cached(
        ("day-summary", netid, days_back, start, end),
        lambda: build_job_day_summary(netid, schedds, days_back, start, end),
    )


@router.get("/users")
async def get_user_range_summary(
    start: str = Query(description=_START_DESCRIPTION, examples=["2026-07-01"]),
    end: str = Query(description=_END_DESCRIPTION, examples=["2026-08-01"]),
) -> UserRangeSummary:
    """Every user who finished a job in the range, busiest first.

    Admin-only by nature, not just for now: the other endpoints answer for one
    owner, while this one is a league table of everybody and there is no version
    of it scoped to a single user. If the router-level gate is ever relaxed, this
    route must keep its own check_is_admin dependency.

    Assembled a day at a time and merged here. Each day is cached on its own, so
    two ranges that overlap -- which is nearly every pair a reader looks at in
    succession -- share everything but the days that differ between them.
    """
    return await build_user_range_summary(start, end)
