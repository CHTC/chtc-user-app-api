"""Access control and parameter handling for the /jobs history endpoints.

The aggregation itself is not exercised here: it needs a reachable Adstash and a
schedd, so both builders are stubbed and what is checked is the part that decides
*who may ask* and *whose* jobs get aggregated. That is the half with a security
consequence.

For now the whole router is admin-only (see the router dependencies in
job_history.py), so a non-admin is refused even for their own jobs. The
per-owner scope inside resolve_owner is still tested through the admin path so
that lifting the gate later is a one-line change rather than a rewrite.
"""

import asyncio
import random
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException

from userapp.api.routes.jobs import _util, job_history


@pytest.fixture(autouse=True)
def stub_builders(monkeypatch):
    """Replace the two aggregations with recorders, and turn the cache off.

    Returns the call log: one dict per call, so a test can assert which owner and
    which schedds the route resolved before any query would have been made.
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

    async def fake_series(owner, schedds, days_back, bin_hours, start=None, end=None):
        calls.append({"endpoint": "series", "owner": owner, "schedds": schedds,
                      "days_back": days_back, "bin_hours": bin_hours,
                      "start": start, "end": end})
        return {**_payload(owner), "binHours": bin_hours, "binsPerDay": 24 // bin_hours, "series": []}

    async def fake_day_summary(owner, schedds, days_back, start=None, end=None):
        calls.append({"endpoint": "day-summary", "owner": owner, "schedds": schedds,
                      "days_back": days_back, "start": start, "end": end})
        payload = _payload(owner)
        payload["sources"]["adstash"]["terminalRecords"] = 0
        payload["sources"]["condorQ"]["stillQueued"] = 0
        return {**payload, "states": [], "clusters": [], "cohorts": [], "activity": [],
                "carry": [], "counted": 0, "skippedOutsideWindow": 0}

    async def fake_user_range_summary(start, end):
        calls.append({"endpoint": "users", "start": start, "end": end})
        # parse_range is the half of the real builder with a decision in it, so
        # it still runs; only the Elasticsearch fan-out below it is replaced.
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


@pytest.fixture
def submit_node_factory(existing_admin_client):
    """Submit nodes that outlive one test's user, cleaned up afterwards."""

    created = []

    def _create(name: str, group_id: int) -> dict:
        response = existing_admin_client.post("/submit_nodes", json={"name": name, "group_id": group_id})
        assert response.status_code == 201, response.text
        node = response.json()
        created.append(node)
        return node

    yield _create

    for node in created:
        existing_admin_client.delete(f"/submit_nodes/{node['id']}")


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


class TestJobsSchedds:

    def test_schedds_come_from_the_owners_submit_nodes(
        self, existing_admin_client, user, group_factory, submit_node_factory, stub_builders,
    ):
        group = group_factory()
        node = submit_node_factory(f"ap{random.randint(1000, 9999)}.chtc.wisc.edu", group["id"])
        existing_admin_client.patch(
            f"/users/{user['id']}",
            json={"submit_nodes": [{"submit_node_id": node["id"]}]},
        )

        existing_admin_client.get("/jobs/series", params={"owner": user["netid"]})

        assert stub_builders[0]["schedds"] == [node["name"]]

    def test_non_hostname_submit_nodes_are_skipped(self, existing_admin_client, user, stub_builders):
        """The `user` fixture's node is named "test-submit-<n>", which names a
        service rather than a schedd; `condor_q -name` could do nothing with it."""

        existing_admin_client.get("/jobs/series", params={"owner": user["netid"]})

        assert stub_builders[0]["schedds"] == []


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
                        maxRequestedMemory=4096, maxUsedMemory=6000,
                        maxRequestedDisk=20 * 1024 * 1024, maxUsedDisk=2 * 1024 * 1024,
                        maxRequestedCpus=16,
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
                        maxRequestedMemory=8192, maxUsedMemory=1200,
                        maxRequestedDisk=4 * 1024 * 1024, maxUsedDisk=None,
                        maxRequestedCpus=8,
                    ),
                    "quiet": self._day(jobs=4, memoryRequested=200, memoryUsed=10),
                },
                "dropped": 0,
            },
        ]
        supplied = iter(days)

        async def fake_fetch(client, day):
            return next(supplied, {"owners": {}, "dropped": 0})

        monkeypatch.setattr(_util, "fetch_user_day", fake_fetch)
        monkeypatch.setattr(_util, "CACHE_SECONDS", 0)
        return days

    @staticmethod
    def _summary():
        return asyncio.run(_util.build_user_range_summary("2026-07-01", "2026-07-03"))

    def test_maxima_take_the_largest_across_days_rather_than_adding(self, two_days):
        row = next(u for u in self._summary()["users"] if u["owner"] == "busy")

        # 4096 on the busy day, 8192 on the quiet one. Summing would say 12288,
        # which is a number no job ever requested.
        assert row["maxRequestedMemoryMb"] == 8192
        assert row["maxUsedMemoryMb"] == 6000
        assert row["maxRequestedCpus"] == 16
        # Disk is stored in KiB and reported in GB.
        assert row["maxRequestedDiskGb"] == pytest.approx(20.0)
        assert row["maxUsedDiskGb"] == pytest.approx(2.0)

    def test_a_maximum_nothing_recorded_is_unknown_not_zero(self, two_days):
        quiet = next(u for u in self._summary()["users"] if u["owner"] == "quiet")

        # Zero would be indistinguishable from a job that really used no disk.
        assert quiet["maxUsedDiskGb"] is None
        assert quiet["maxRequestedCpus"] is None

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

        # 8100 + 100 CPU seconds over 9000 + 1000 slot seconds. Averaging the
        # two days' own ratios (90% and 10%) would say 50%.
        assert row["cpuPct"] == pytest.approx(82.0)
        # 900 MB used of 2000 requested; the quiet day used none of its 1000.
        assert row["memoryPct"] == pytest.approx(45.0)
        assert row["removedPct"] == pytest.approx(10.0)
        assert row["avgRuntimeSeconds"] == pytest.approx(5.5)

    def test_a_user_present_on_only_one_day_still_appears(self, two_days):
        summary = self._summary()

        assert [u["owner"] for u in summary["users"]] == ["busy", "quiet"], "busiest first"
        assert summary["totalUsers"] == 2
        assert summary["days"] == 2

    def test_an_absent_denominator_reads_as_unknown_not_as_zero(self, two_days):
        quiet = next(u for u in self._summary()["users"] if u["owner"] == "quiet")

        # No slot time was recorded, so its CPU efficiency is not known. Zero
        # would claim the opposite -- that every core it bought sat idle.
        assert quiet["cpuPct"] is None
        assert quiet["memoryPct"] == pytest.approx(5.0)

    def test_a_truncated_day_truncates_the_range(self, monkeypatch, two_days):
        async def fake_fetch(client, day):
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
