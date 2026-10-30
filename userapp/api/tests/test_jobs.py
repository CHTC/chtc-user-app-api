"""Access control and parameter handling for the /jobs history endpoints.

The queries themselves are not exercised here: they need a reachable htcondordb,
so the builders are stubbed and what is checked is the part that decides *who may
ask* and *whose* jobs get aggregated. That is the half with a security
consequence. The arithmetic that folds query results into payloads is pure, and
is tested directly further down.

For now the whole router is admin-only (see the router dependencies in
job_history.py), so a non-admin is refused even for their own jobs. The
per-owner scope inside resolve_owner is still tested through the admin path so
that lifting the gate later is a one-line change rather than a rewrite.
"""

import asyncio
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException

from userapp.api.routes.jobs import _util, job_history


@pytest.fixture(autouse=True)
def stub_builders(monkeypatch):
    """Replace the two aggregations with recorders, and turn the cache off.

    Returns the call log: one dict per call, so a test can assert which owner the
    route resolved before any query would have been made.
    """

    calls = []

    def _payload(owner: str) -> dict:
        return {
            "owner": owner,
            "generatedAt": "2026-08-24T00:00:00-05:00",
            "timezone": _util.TIMEZONE,
            "days": ["2026-08-24"],
            "batches": [],
            "sources": {
                "adstash": {"host": "es", "index": "idx"},
                "condorQ": {"pool": "p", "schedd": "none", "schedds": [], "liveAds": 0},
            },
        }

    async def fake_series(owner, days_back, bin_hours, start=None, end=None):
        calls.append({"endpoint": "series", "owner": owner,
                      "days_back": days_back, "bin_hours": bin_hours,
                      "start": start, "end": end})
        return {**_payload(owner), "binHours": bin_hours, "binsPerDay": 24 // bin_hours, "series": []}

    async def fake_day_summary(owner, days_back, start=None, end=None):
        calls.append({"endpoint": "day-summary", "owner": owner,
                      "days_back": days_back, "start": start, "end": end})
        payload = _payload(owner)
        payload["sources"]["adstash"]["terminalRecords"] = 0
        payload["sources"]["condorQ"]["stillQueued"] = 0
        return {**payload, "states": [], "clusters": [], "cohorts": [], "activity": [],
                "carry": [], "counted": 0, "placedBeforeWindow": 0}

    async def fake_user_range_summary(start, end):
        calls.append({"endpoint": "users", "start": start, "end": end})
        # parse_range is the half of the real builder with a decision in it, so
        # it still runs; only the htcondordb fan-out below it is replaced.
        first, last = _util.parse_range(start, end)
        return {
            "start": first.isoformat(), "end": last.isoformat(),
            "days": (last - first).days, "timezone": _util.TIMEZONE,
            "generatedAt": "2026-08-24T00:00:00-05:00",
            "users": [], "totalUsers": 0, "truncated": False,
            "source": {"host": "es", "index": "idx"},
        }

    monkeypatch.setattr(job_history, "build_job_series", fake_series)
    monkeypatch.setattr(job_history, "build_job_day_summary", fake_day_summary)
    monkeypatch.setattr(job_history, "build_user_range_summary", fake_user_range_summary)
    # Otherwise the first test's answer would be served to every later one.
    monkeypatch.setattr(_util, "CACHE_SECONDS", 0)
    return calls


class TestJobsAuthentication:

    def test_series_requires_authentication(self, api_client):
        assert api_client.get("/jobs/series").status_code == 401

    def test_day_summary_requires_authentication(self, api_client):
        assert api_client.get("/jobs/day-summary").status_code == 401


class TestJobsAdminOnly:
    """The router is gated on admin while the feature is being tested.

    A signed-in non-admin is refused everywhere, including for their own jobs.
    When the gate is lifted these become the per-owner scope tests again: own
    jobs 200, someone else's 403.
    """

    @pytest.mark.parametrize("endpoint", ["/jobs/series", "/jobs/day-summary"])
    def test_a_non_admin_is_refused_for_their_own_jobs(self, nonadmin_client, user, endpoint, stub_builders):
        response = nonadmin_client.get(endpoint)

        assert response.status_code == 403, response.text
        assert stub_builders == [], "nothing should be aggregated for a refused caller"

    def test_a_non_admin_is_refused_when_naming_themselves(self, nonadmin_client, user):
        response = nonadmin_client.get("/jobs/series", params={"owner": user["netid"]})

        assert response.status_code == 403

    def test_a_non_admin_is_refused_when_naming_someone_else(self, nonadmin_client, user, user_factory, project):
        other = user_factory(1, project_id=project["id"])

        response = nonadmin_client.get("/jobs/series", params={"owner": other["netid"]})

        assert response.status_code == 403


class TestJobsOwnerScope:
    """Which netid an admin's request resolves to."""

    def test_admin_defaults_to_their_own_netid(self, admin_client, admin_user, stub_builders):
        response = admin_client.get("/jobs/series")

        assert response.status_code == 200, response.text
        assert response.json()["owner"] == admin_user["netid"]
        assert stub_builders[0]["owner"] == admin_user["netid"]

    def test_admin_may_name_another_user(self, existing_admin_client, user, stub_builders):
        response = existing_admin_client.get("/jobs/series", params={"owner": user["netid"]})

        assert response.status_code == 200, response.text
        assert response.json()["owner"] == user["netid"]
        assert stub_builders[0]["owner"] == user["netid"]

    def test_day_summary_resolves_the_owner_the_same_way(self, existing_admin_client, user):
        response = existing_admin_client.get("/jobs/day-summary", params={"owner": user["netid"]})

        assert response.status_code == 200, response.text
        assert response.json()["owner"] == user["netid"]

    def test_unknown_netid_is_a_404(self, existing_admin_client):
        response = existing_admin_client.get("/jobs/series", params={"owner": "no-such-netid"})

        assert response.status_code == 404

    def test_an_admin_without_a_netid_cannot_default_to_themselves(self, existing_admin_client):
        # The seed admin has no netid on record, so there is no Owner to query.
        response = existing_admin_client.get("/jobs/series")

        assert response.status_code == 409


class TestJobsParameters:

    def test_defaults_are_applied(self, existing_admin_client, user, stub_builders):
        existing_admin_client.get("/jobs/series", params={"owner": user["netid"]})

        assert stub_builders[0]["days_back"] == _util.DEFAULT_DAYS_BACK
        assert stub_builders[0]["bin_hours"] == _util.DEFAULT_BIN_HOURS

    def test_window_and_bin_width_are_passed_through(self, existing_admin_client, user, stub_builders):
        response = existing_admin_client.get(
            "/jobs/series", params={"owner": user["netid"], "days_back": 7, "bin_hours": 12}
        )

        assert response.status_code == 200, response.text
        assert stub_builders[0]["days_back"] == 7
        assert stub_builders[0]["bin_hours"] == 12
        assert response.json()["binsPerDay"] == 2

    @pytest.mark.parametrize("days_back", [0, _util.MAX_DAYS_BACK + 1])
    def test_window_is_bounded(self, existing_admin_client, user, days_back):
        response = existing_admin_client.get(
            "/jobs/series", params={"owner": user["netid"], "days_back": days_back}
        )

        assert response.status_code == 422

    def test_bin_width_must_divide_a_day(self, existing_admin_client, user):
        response = existing_admin_client.get(
            "/jobs/series", params={"owner": user["netid"], "bin_hours": 5}
        )

        assert response.status_code == 422


class TestUserRangeAccess:
    """/jobs/users is the one endpoint here that is about everybody.

    The other two are admin-only for now and may later let a user ask about
    themselves. This one has no per-user version to fall back to, which makes
    admin the whole of its access rule whatever happens to the router gate.
    """

    RANGE = {"start": "2026-07-01", "end": "2026-08-01"}

    def test_requires_authentication(self, api_client):
        assert api_client.get("/jobs/users", params=self.RANGE).status_code == 401

    def test_a_non_admin_may_not_read_it(self, nonadmin_client, user):
        response = nonadmin_client.get("/jobs/users", params=self.RANGE)

        assert response.status_code == 403, "the table covers every user, not just the caller"

    def test_an_admin_may_read_it(self, existing_admin_client, stub_builders):
        response = existing_admin_client.get("/jobs/users", params=self.RANGE)

        assert response.status_code == 200, response.text
        assert response.json()["days"] == 31
        assert stub_builders[0]["start"] == "2026-07-01"

    @pytest.mark.parametrize("params", [
        {},
        {"start": "2026-07-01"},
        {"end": "2026-08-01"},
    ])
    def test_both_bounds_are_required(self, existing_admin_client, params):
        assert existing_admin_client.get("/jobs/users", params=params).status_code == 422

    @pytest.mark.parametrize("start", ["2026-07", "07-01-2026", "July", "2026-13-01", ""])
    def test_a_malformed_date_is_rejected(self, existing_admin_client, start):
        response = existing_admin_client.get("/jobs/users", params={"start": start, "end": "2026-08-01"})

        assert response.status_code == 422, f"{start!r} should not be accepted"

    def test_an_end_before_the_start_is_rejected(self, existing_admin_client):
        response = existing_admin_client.get(
            "/jobs/users", params={"start": "2026-08-01", "end": "2026-07-01"}
        )

        assert response.status_code == 422
        assert "after" in response.json()["detail"]

    def test_an_empty_range_is_rejected(self, existing_admin_client):
        # start == end would ask about no days at all, which is a mistake rather
        # than a request for an empty table.
        response = existing_admin_client.get(
            "/jobs/users", params={"start": "2026-07-01", "end": "2026-07-01"}
        )

        assert response.status_code == 422

    def test_a_range_longer_than_the_cap_is_rejected(self, existing_admin_client):
        response = existing_admin_client.get(
            "/jobs/users", params={"start": "2020-01-01", "end": "2026-01-01"}
        )

        assert response.status_code == 422
        assert str(_util.MAX_RANGE_DAYS) in response.json()["detail"]

    def test_a_start_in_the_future_is_rejected(self, existing_admin_client):
        ahead = datetime.now(_util.TZ).date() + timedelta(days=10)

        response = existing_admin_client.get(
            "/jobs/users",
            params={"start": ahead.isoformat(), "end": (ahead + timedelta(days=1)).isoformat()},
        )

        assert response.status_code == 422
        assert "future" in response.json()["detail"]


class TestRangeDays:
    """The day grid a range is assembled from.

    Days, not weeks: they tile an arbitrary range exactly, and they are the unit
    that is cached, so two overlapping ranges share everything but their
    difference.
    """

    def test_a_range_is_every_day_from_start_up_to_but_not_including_end(self):
        days = _util.range_days(date(2026, 7, 1), date(2026, 7, 5))

        assert days == [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3), date(2026, 7, 4)]

    def test_consecutive_ranges_tile_without_overlapping(self):
        first = _util.range_days(date(2026, 7, 1), date(2026, 7, 8))
        second = _util.range_days(date(2026, 7, 8), date(2026, 7, 15))

        assert not set(first) & set(second), "an exclusive end is what stops double counting"
        assert first[-1] == date(2026, 7, 7)

    def test_overlapping_ranges_share_their_common_days(self):
        first = set(_util.range_days(date(2026, 7, 1), date(2026, 8, 1)))
        shifted = set(_util.range_days(date(2026, 7, 2), date(2026, 8, 2)))

        # 30 of 31 days are reused, which is the whole reason days are cached.
        assert len(first & shifted) == 30

    def test_a_range_spanning_a_dst_transition_still_has_whole_days(self):
        # 2026-11-01 is the US fall-back day: 25 hours long. Bounds come from
        # local midnights, so the day is the length it really was.
        day = date(2026, 11, 1)
        length = _util._midnight(day + timedelta(days=1)) - _util._midnight(day)

        assert length == 25 * 3600

    def test_a_finished_day_is_cached_for_longer_than_today(self, monkeypatch):
        monkeypatch.setattr(_util, "CACHE_SECONDS", 60)
        today = datetime.now(_util.TZ).date()

        assert _util.day_cache_ttl(today - timedelta(days=1)) == _util.DAY_CACHE_SECONDS_PAST
        assert _util.day_cache_ttl(today) == 60


class TestUserRangeAggregation:
    """Folding the days back into one row per user.

    Every column is a sum or a count precisely so that this merge is exact. The
    ratios are the part worth pinning down: they have to come from summed
    numerators over summed denominators, not from averaging each day's ratio,
    which would weight a quiet day the same as a busy one.
    """

    @staticmethod
    def _day(**totals):
        base = _util._empty_totals()
        base.update(totals)
        return base

    @pytest.fixture
    def two_days(self, monkeypatch):
        """A user with one busy, efficient day and one quiet, wasteful one."""

        days = [
            {
                "owners": {
                    "busy": self._day(
                        jobs=900, removed=90, held=9, failed=45, retried=18,
                        slotSeconds=9000, wallSeconds=4500, userCpu=8000, sysCpu=100,
                        memoryUsed=900, memoryRequested=1000,
                        diskUsed=2 * 1024 * 1024, diskRequested=20 * 1024 * 1024,
                        cpusRequested=1800,
                    )
                },
                "dropped": 0,
            },
            {
                "owners": {
                    "busy": self._day(
                        jobs=100, removed=10, held=1, failed=5, retried=2,
                        slotSeconds=1000, wallSeconds=1000, userCpu=100, sysCpu=0,
                        memoryUsed=0, memoryRequested=1000,
                        diskRequested=4 * 1024 * 1024,
                        cpusRequested=100,
                    ),
                    "quiet": self._day(jobs=4, memoryRequested=200, memoryUsed=10),
                },
                "dropped": 0,
            },
        ]
        supplied = iter(days)

        async def fake_fetch(day):
            return next(supplied, {"owners": {}, "dropped": 0})

        monkeypatch.setattr(_util, "fetch_user_day", fake_fetch)
        monkeypatch.setattr(_util, "CACHE_SECONDS", 0)
        return days

    @staticmethod
    def _summary():
        return asyncio.run(_util.build_user_range_summary("2026-07-01", "2026-07-03"))

    def test_resources_are_summed_and_reported_in_gb(self, two_days):
        row = next(u for u in self._summary()["users"] if u["owner"] == "busy")

        # Memory is recorded in MB, disk in KiB; both come back as GB summed
        # over every job in the range.
        assert row["memoryRequestedGb"] == pytest.approx(2000 / 1024)
        assert row["memoryUsedGb"] == pytest.approx(900 / 1024)
        assert row["diskRequestedGb"] == pytest.approx(24.0)
        assert row["diskUsedGb"] == pytest.approx(2.0)
        assert row["cpusRequested"] == 1900

    def test_counts_are_the_sum_of_their_days(self, two_days):
        row = next(u for u in self._summary()["users"] if u["owner"] == "busy")

        assert row["jobs"] == 1000
        assert row["removed"] == 100
        assert row["held"] == 10
        assert row["failed"] == 50
        assert row["retried"] == 20
        assert row["coreHours"] == pytest.approx(10000 / 3600)

    def test_ratios_divide_summed_totals_rather_than_averaging_days(self, two_days):
        row = next(u for u in self._summary()["users"] if u["owner"] == "busy")

        # 900 MB used of 2000 requested; the quiet day used none of its 1000.
        # Averaging the two days' own ratios (90% and 0%) would say 45% too, so
        # disk is the case that tells them apart: 2 GB of 24 is 8.3%, where the
        # days' own ratios (10% and 0%) average to 5%.
        assert row["memoryPct"] == pytest.approx(45.0)
        assert row["diskPct"] == pytest.approx(100 * 2 / 24)
        assert row["removedPct"] == pytest.approx(10.0)
        assert row["avgRuntimeSeconds"] == pytest.approx(5.5)

    def test_a_user_present_on_only_one_day_still_appears(self, two_days):
        summary = self._summary()

        assert [u["owner"] for u in summary["users"]] == ["busy", "quiet"], "busiest first"
        assert summary["totalUsers"] == 2
        assert summary["days"] == 2

    def test_an_absent_denominator_reads_as_unknown_not_as_zero(self, two_days):
        quiet = next(u for u in self._summary()["users"] if u["owner"] == "quiet")

        # No disk was requested, so how much of it was used is not known. Zero
        # would claim the opposite -- that every byte it asked for sat empty.
        assert quiet["diskPct"] is None
        assert quiet["memoryPct"] == pytest.approx(5.0)

    def test_a_truncated_day_truncates_the_range(self, monkeypatch, two_days):
        async def fake_fetch(day):
            return {"owners": {}, "dropped": 17}

        monkeypatch.setattr(_util, "fetch_user_day", fake_fetch)

        assert self._summary()["truncated"] is True, "a partial answer must not read as complete"


class TestCalendarWindow:
    """Which days the job viewer draws.

    The viewer used to be able to look only backwards from today, which made it
    answer the wrong question when it was opened from a range in the past: with
    a default of 34 days back, clicking into a user from a July range showed the
    three days of July nearest today and then five weeks that were not asked for.
    """

    def test_days_back_still_ends_today(self):
        calendar = _util.build_calendar(_util.DEFAULT_DAYS_BACK)
        today = datetime.now(_util.TZ).date()

        assert calendar.days[-1] == today.isoformat()
        assert len(calendar.days) == _util.DEFAULT_DAYS_BACK + 1, "both ends are inclusive"

    def test_an_explicit_range_is_exactly_that_range(self):
        calendar = _util.build_calendar_for_range("2026-07-01", "2026-08-01")

        assert calendar.days[0] == "2026-07-01"
        assert calendar.days[-1] == "2026-07-31", "the exclusive end must not appear"
        assert len(calendar.days) == 31
        assert all(day.startswith("2026-07") for day in calendar.days)

    def test_the_exclusive_end_matches_the_user_table(self):
        # The table hands its own [start, end) straight to the calendar link, so
        # the two must read one pair of dates the same way.
        table = _util.range_days(*_util.parse_range("2026-07-01", "2026-08-01"))
        calendar = _util.build_calendar_for_range("2026-07-01", "2026-08-01")

        assert [day.isoformat() for day in table] == calendar.days

    def test_a_single_day_is_a_valid_window(self):
        calendar = _util.build_calendar_for_range("2026-07-15", "2026-07-16")

        assert calendar.days == ["2026-07-15"]

    def test_a_range_longer_than_the_viewer_holds_is_refused(self):
        # The table summarises up to a year; this view cannot draw one.
        with pytest.raises(HTTPException) as raised:
            _util.build_calendar_for_range("2026-03-05", "2026-09-01")

        assert raised.value.status_code == 422
        assert str(_util.MAX_DAYS_BACK) in raised.value.detail

    def test_a_dst_day_is_the_length_it_really_was(self):
        # Both transitions, and both in the past: parse_range refuses a start in
        # the future, since there is no history to report from one.
        fall_back = _util.build_calendar_for_range("2025-11-02", "2025-11-03", bin_hours=1)
        spring_forward = _util.build_calendar_for_range("2026-03-08", "2026-03-09", bin_hours=1)

        assert fall_back.days == ["2025-11-02"]
        assert fall_back.end_sec - fall_back.start_sec == 25 * 3600
        assert spring_forward.end_sec - spring_forward.start_sec == 23 * 3600

    def test_a_window_starting_in_the_future_is_refused(self):
        ahead = (datetime.now(_util.TZ).date() + timedelta(days=10)).isoformat()
        beyond = (datetime.now(_util.TZ).date() + timedelta(days=11)).isoformat()

        with pytest.raises(HTTPException) as raised:
            _util.build_calendar_for_range(ahead, beyond)

        assert raised.value.status_code == 422


class TestCalendarRangeParameters:
    """start and end on the two per-owner endpoints."""

    def test_a_range_reaches_the_builder(self, existing_admin_client, user, stub_builders):
        response = existing_admin_client.get(
            "/jobs/series",
            params={"owner": user["netid"], "start": "2026-07-01", "end": "2026-08-01"},
        )

        assert response.status_code == 200, response.text
        assert stub_builders[0]["start"] == "2026-07-01"
        assert stub_builders[0]["end"] == "2026-08-01"

    def test_omitting_both_keeps_the_days_back_behaviour(self, existing_admin_client, user, stub_builders):
        response = existing_admin_client.get("/jobs/series", params={"owner": user["netid"]})

        assert response.status_code == 200, response.text
        assert stub_builders[0]["start"] is None and stub_builders[0]["end"] is None

    @pytest.mark.parametrize("endpoint", ["/jobs/series", "/jobs/day-summary"])
    @pytest.mark.parametrize("params", [{"start": "2026-07-01"}, {"end": "2026-08-01"}])
    def test_one_bound_without_the_other_is_rejected(
        self, existing_admin_client, user, endpoint, params
    ):
        response = existing_admin_client.get(
            endpoint, params={"owner": user["netid"], **params}
        )

        assert response.status_code == 422
        assert "together" in response.json()["detail"]

    def test_the_range_is_part_of_the_cache_key(self, existing_admin_client, user, stub_builders):
        # Two windows are two different answers; serving one from the other's
        # cache entry is how a page ends up showing a month it did not ask for.
        base = {"owner": user["netid"]}
        existing_admin_client.get("/jobs/series", params={**base, "start": "2026-07-01", "end": "2026-08-01"})
        existing_admin_client.get("/jobs/series", params={**base, "start": "2026-06-01", "end": "2026-07-01"})

        windows = [(call.get("start"), call.get("end")) for call in stub_builders]
        assert ("2026-07-01", "2026-08-01") in windows
        assert ("2026-06-01", "2026-07-01") in windows


class TestWindowSides:
    """A past window has jobs on both sides of it, and the two sides differ."""

    def setup_method(self):
        self.week = _util.build_calendar_for_range("2026-08-28", "2026-09-04")

    def test_clamped_index_tells_before_from_after(self):
        week = self.week

        assert week.day_index_clamped(week.start_sec - 1) == -1
        assert week.day_index_clamped(week.start_sec) == 0
        assert week.day_index_clamped(week.end_sec - 1) == 6
        assert week.day_index_clamped(week.end_sec) == len(week) == 7
        assert week.day_index_clamped("junk") == -1

    def test_the_plain_index_folds_both_sides_together(self):
        # What the clamped variant exists to fix; kept as documentation.
        week = self.week

        assert week.day_index(week.start_sec - 1) == -1
        assert week.day_index(week.end_sec) == -1

    def test_day_key_names_days_outside_the_window(self):
        week = self.week

        assert week.day_key(week.start_sec - 3600) == "2026-08-27"
        assert week.day_key(week.end_sec + 3600) == "2026-09-04"
        assert week.day_key(0) is None
        assert week.day_key(None) is None


class TestOverlapSelection:
    """Which jobs a window selects: everything open at some point inside it."""

    def setup_method(self):
        self.week = _util.build_calendar_for_range("2026-08-28", "2026-09-04")

    def test_terminal_records_are_kept_when_they_outlive_the_window(self):
        week = self.week
        before, inside, after = week.start_sec - 90 * _util.DAY_SECONDS, week.start_sec, week.end_sec

        assert week.open_inside(before, after), "placed long before and finished after: open throughout"
        assert week.open_inside(before, inside), "finished inside"
        assert week.open_inside(inside, inside), "placed inside"
        assert not week.open_inside(before, inside - 1), "finished before the window opened"
        assert not week.open_inside(after, after), "placed after the window closed"

    def test_hour_buckets_sit_on_the_same_side_of_an_edge_as_their_jobs(self):
        # The selection runs on hour buckets, floored to the UTC hour. Exact only
        # because every edge the calendar draws is on the hour.
        week = self.week
        assert week.start_sec % _util.BUCKET_SECONDS == 0
        assert week.end_sec % _util.BUCKET_SECONDS == 0
        assert all(edge % _util.BUCKET_SECONDS == 0 for edge in week.bin_boundaries)

        last_hour_before = week.start_sec - _util.BUCKET_SECONDS
        assert not week.open_inside(last_hour_before, last_hour_before)

    def test_live_ads_are_kept_when_placed_before_the_window_closed(self):
        week = self.week
        ads = {
            "old": {"QDate": week.start_sec - 90 * _util.DAY_SECONDS},
            "inside": {"QDate": week.end_sec - 1},
            "later": {"QDate": week.end_sec},
            "unknown": {},
        }

        selected = _util.live_ads_in_window(ads, week)

        assert set(selected) == {"old", "inside", "unknown"}


class TestDayAggregatorAcrossWindows:
    """The day summary for one window is complete on its own, so consecutive
    windows can be stitched together by a viewer."""

    def setup_method(self):
        self.week = _util.build_calendar_for_range("2026-08-28", "2026-09-04")
        self.D = len(self.week)

    def _payload(self, aggregator):
        return aggregator.to_payload("alice", {})

    def _carry(self, payload):
        return {row["day"]: row for row in payload["carry"]}

    def test_a_job_that_outlives_the_window_holds_its_place_every_day(self):
        aggregator = _util._DayAggregator(self.week)
        aggregator.add(
            9, -1, queue_key="2026-08-27",
            run_from_day=-1, started_day=-1, end_day=self.D,
            end_state=_util.STATE_COMPLETED, count=5, ever_ran=False, has_end=True,
        )

        payload = self._payload(aggregator)
        carry = self._carry(payload)

        assert carry[_util.WINDOW_START_DAY]["placed"] == 5
        for day in self.week.days:
            assert (carry[day]["placed"], carry[day]["active"]) == (5, 0), day
        assert payload["activity"] == [], "nothing moved inside the window"
        assert payload["counted"] == 0
        assert payload["placedBeforeWindow"] == 5

        (cohort,) = payload["cohorts"]
        assert cohort["day"] == "2026-08-27", "filed under its real placement day"
        assert cohort["queued"] == 5
        assert cohort["asOf"][self.week.days[0]] == (5, 0, 0, 0)
        assert cohort["asOf"][self.week.days[-1]] == (5, 0, 0, 0)

        (cluster,) = payload["clusters"]
        assert cluster["total"] == 0, "total counts placements inside the window"
        assert cluster["firstQueued"] == "2026-08-27"

    def test_a_start_after_the_window_reads_as_queued_throughout(self):
        aggregator = _util._DayAggregator(self.week)
        aggregator.add(
            9, -1, queue_key="2026-08-27",
            run_from_day=self.D, started_day=self.D, end_day=self.D,
            count=2, ever_ran=True, has_end=True,
        )

        payload = self._payload(aggregator)
        carry = self._carry(payload)

        for day in self.week.days:
            assert (carry[day]["placed"], carry[day]["active"]) == (2, 0), day
        assert payload["activity"] == []
        assert all(states == (2, 0, 0, 0) for states in payload["cohorts"][0]["asOf"].values())

    def test_a_start_before_the_window_reads_as_running_throughout(self):
        aggregator = _util._DayAggregator(self.week)
        aggregator.add(
            9, -1, queue_key="2026-08-20",
            run_from_day=-1, started_day=-1, end_day=self.D,
            count=3, ever_ran=True, has_end=True,
        )

        carry = self._carry(self._payload(aggregator))

        assert carry[_util.WINDOW_START_DAY]["active"] == 3
        for day in self.week.days:
            assert (carry[day]["placed"], carry[day]["active"]) == (0, 3), day

    def test_a_job_that_ended_before_the_window_holds_no_place(self):
        aggregator = _util._DayAggregator(self.week)
        aggregator.add(
            9, -1, queue_key="2026-08-20",
            run_from_day=-1, started_day=-1, end_day=-1,
            count=3, ever_ran=True, has_end=True,
        )

        payload = self._payload(aggregator)

        assert payload["carry"] == []
        assert payload["activity"] == []

    def test_a_job_inside_the_window_is_reported_as_before(self):
        aggregator = _util._DayAggregator(self.week)
        days = self.week.days
        aggregator.add(9, 1, queue_key=days[1], run_from_day=2, started_day=2, end_day=4, count=4)

        payload = self._payload(aggregator)

        activity = {row["day"]: row for row in payload["activity"]}
        assert activity[days[2]]["started"] == 4
        assert activity[days[4]]["completed"] == 4

        (cohort,) = payload["cohorts"]
        assert cohort["day"] == days[1]
        assert cohort["asOf"][days[1]] == (4, 0, 0, 0)
        assert cohort["asOf"][days[3]] == (0, 4, 0, 0)
        assert cohort["asOf"][days[4]] == (0, 0, 4, 0)

        carry = self._carry(payload)
        assert (carry[days[1]]["placed"], carry[days[1]]["active"]) == (4, 0)
        assert (carry[days[3]]["placed"], carry[days[3]]["active"]) == (0, 4)
        assert days[4] not in carry, "terminal from its end day on"
        assert payload["counted"] == 4
        assert payload["placedBeforeWindow"] == 0

    def test_two_windows_agree_where_they_meet(self):
        # One job seen from the week it was placed in and from the week after:
        # placed on the last day of A, started and finished inside B.
        week_a = _util.build_calendar_for_range("2026-08-21", "2026-08-28")
        week_b = self.week
        placed = "2026-08-27"

        in_a = _util._DayAggregator(week_a)
        in_a.add(
            9, 6, queue_key=placed,
            run_from_day=len(week_a), started_day=len(week_a), end_day=len(week_a),
            count=1, ever_ran=True, has_end=True,
        )
        in_b = _util._DayAggregator(week_b)
        in_b.add(9, -1, queue_key=placed, run_from_day=1, started_day=1, end_day=3, count=1)

        payload_a = self._payload(in_a)
        payload_b = self._payload(in_b)

        # A's last-day census is B's opening census.
        carry_a = self._carry(payload_a)
        carry_b = self._carry(payload_b)
        assert carry_a[week_a.days[-1]] == {"cluster": 9, "day": week_a.days[-1], "placed": 1, "active": 0}
        assert carry_b[_util.WINDOW_START_DAY] == {"cluster": 9, "day": _util.WINDOW_START_DAY, "placed": 1, "active": 0}

        # Both file it under the same cohort day, and each covers its own days.
        (cohort_a,) = payload_a["cohorts"]
        (cohort_b,) = payload_b["cohorts"]
        assert cohort_a["day"] == cohort_b["day"] == placed
        assert cohort_a["asOf"] == {placed: (1, 0, 0, 0)}
        assert cohort_b["asOf"][week_b.days[0]] == (1, 0, 0, 0)
        assert cohort_b["asOf"][week_b.days[1]] == (0, 1, 0, 0)
        assert cohort_b["asOf"][week_b.days[3]] == (0, 0, 1, 0)

        # The transition lands in the week it happened, and only there.
        assert payload_a["activity"] == []
        assert [row["day"] for row in payload_b["activity"]] == [week_b.days[1], week_b.days[3]]

    def test_a_start_before_the_window_is_running_in_the_cohort_too(self):
        # The census already knew this (see the running-throughout test); the
        # cohort's own states have to agree with it, or the same cohort reads
        # as running in one week and queued in the next.
        aggregator = _util._DayAggregator(self.week)
        aggregator.add(
            9, -1, queue_key="2026-08-20",
            run_from_day=0, started_day=-1, end_day=3,
            count=3, ever_ran=True, has_end=True,
        )

        (cohort,) = self._payload(aggregator)["cohorts"]

        assert cohort["asOf"][self.week.days[0]] == (0, 3, 0, 0)
        assert cohort["asOf"][self.week.days[2]] == (0, 3, 0, 0)
        assert cohort["asOf"][self.week.days[3]] == (0, 0, 3, 0)


class TestHistoryFolding:
    """Turning htcondordb's grouped rows into the counts the builders use.

    db_query is replaced by a recorder that answers from canned rows, so these
    check the folding rather than the database.
    """

    def setup_method(self):
        self.week = _util.build_calendar_for_range("2026-08-28", "2026-09-04")

    @staticmethod
    def _fake_db(monkeypatch, answer):
        """Install a db_query that answers `answer(sql, params)` and logs each call."""
        calls = []

        async def fake(sql, params=()):
            calls.append((sql, list(params)))
            return answer(sql, list(params))

        monkeypatch.setattr(_util, "db_query", fake)
        return calls

    def test_jobs_that_never_ran_are_the_group_less_the_ones_that_did(self):
        q, e = 1000 * 3600, 1010 * 3600
        terminal = {(9, False, q, e): 10, (9, True, q, e): 4, (11, False, q, e): 2}
        started = {
            (9, False, q, q + 3600, e): 6,
            (9, False, q, q + 7200, e): 1,
            (9, True, q, q + 3600, e): 4,
            # A record ingested between the two queries: clamped, not negative.
            (11, False, q, q + 3600, e): 3,
        }

        assert _util.never_started(terminal, started) == {(9, False, q, e): 3}

    def test_terminal_groups_keep_only_jobs_open_inside_the_window(self, monkeypatch):
        week = self.week
        hour = _util.BUCKET_SECONDS
        rows = [
            (9, week.start_sec - 50 * hour, week.start_sec + hour, 5),   # placed before, ended inside
            (9, week.start_sec - 50 * hour, week.start_sec - hour, 7),   # ended before: not here
            (10, week.start_sec + hour, week.end_sec + hour, 2),         # placed inside, ended after
        ]
        calls = self._fake_db(monkeypatch, lambda sql, params: rows if "== 3" in sql else [])

        groups = asyncio.run(_util.fetch_terminal_groups("alice", week, snapshot=week.end_sec + 99))

        assert groups == {
            (9, True, week.start_sec - 50 * hour, week.start_sec + hour): 5,
            (10, True, week.start_sec + hour, week.end_sec + hour): 2,
        }
        # Removed and the rest are asked for separately, both bounded by the
        # window's start below and the snapshot above.
        assert len(calls) == 2
        assert all(params == ["alice", week.start_sec, week.end_sec + 99] for _, params in calls)

    @staticmethod
    def _user_day_answer(main, memory, disk):
        """Answer each of a user day's three queries from its own canned rows."""
        def answer(sql, params):
            if "RequestMemory" in sql:
                return memory
            if "RequestDisk" in sql:
                return disk
            return main
        return answer

    def test_a_user_day_maps_each_column_and_converts_resident_memory(self, monkeypatch):
        main = [
            # removed, held, failed, retried, then slot, wall, user, sys, RSS (KiB), disk used, cpus
            ("alice", 12, 1, 2, 3, 4, 3600, 50, 40, 5, 2048 * 1024, 10, 8),
            # htcondordb's way of failing to aggregate: owners merged, no Owner.
            (None, 30, 0, 0, 0, 0, None, None, None, None, None, None, None),
        ]
        self._fake_db(monkeypatch, self._user_day_answer(main, [("alice", 4096)], [("alice", 20)]))

        day = asyncio.run(_util.fetch_user_day(date(2026, 8, 28)))

        alice = day["owners"]["alice"]
        assert (alice["jobs"], alice["removed"], alice["held"], alice["failed"], alice["retried"]) == (12, 1, 2, 3, 4)
        assert alice["slotSeconds"] == 3600
        assert alice["memoryUsed"] == 2048, "ResidentSetSize is KiB; the table wants MB"
        assert alice["memoryRequested"] == 4096
        assert (alice["diskUsed"], alice["diskRequested"]) == (10, 20)
        assert alice["cpusRequested"] == 8
        assert "None" not in day["owners"]
        assert day["dropped"] == 30, "the merged row marks the range truncated"

    def test_a_request_that_could_not_be_summed_leaves_out_that_resource_only(self, monkeypatch):
        main = [("alice", 12, 0, 0, 0, 0, 3600, 50, 40, 5, 2048 * 1024, 10, 8)]
        # alice's RequestMemory sum met an expression and was merged away.
        memory = [(None, 12)]
        self._fake_db(monkeypatch, self._user_day_answer(main, memory, [("alice", 20)]))

        day = asyncio.run(_util.fetch_user_day(date(2026, 8, 28)))

        alice = day["owners"]["alice"]
        # Used without requested would make the percentage compare different
        # jobs, so both go.
        assert (alice["memoryUsed"], alice["memoryRequested"]) == (0, 0)
        assert (alice["diskUsed"], alice["diskRequested"]) == (10, 20), "disk is unaffected"
        assert alice["jobs"] == 12
        assert day["dropped"] == 0, "the user is still all there"

    def test_live_jobs_already_in_history_are_dropped(self, monkeypatch):
        live = [
            (9, 0, 100, 2, 90, 90, "batch"),
            (9, 1, 100, 1, None, 100, None),
        ]

        def answer(sql, params):
            if f"FROM {_util.JOBS_TABLE}" in sql:
                return live
            return [(9, 1)]  # 9.1 finished and is already in history

        self._fake_db(monkeypatch, answer)

        jobs, errors, snapshot = asyncio.run(_util.query_live_jobs("alice"))

        assert list(jobs) == ["9.0"]
        assert jobs["9.0"]["JobBatchName"] == "batch"
        assert errors == []
        assert snapshot > 0

    def test_a_failed_live_read_is_an_understatement_not_an_error(self, monkeypatch):
        async def failing(sql, params=()):
            raise HTTPException(status_code=502, detail="htcondordb query failed: boom")

        monkeypatch.setattr(_util, "db_query", failing)

        jobs, errors, _ = asyncio.run(_util.query_live_jobs("alice"))

        assert jobs == {}
        assert errors == [f"{_util.HTCONDORDB_SCHEDD}: htcondordb query failed: boom"]
