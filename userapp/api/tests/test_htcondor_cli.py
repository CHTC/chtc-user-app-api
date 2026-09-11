import asyncio
import json
import sys
from datetime import datetime, timedelta

import pytest

from userapp.api.util import htcondor_cli
from userapp.api.util.htcondor_cli import ScheddError, ScheddTimeout, condor_q


class FakeProc:
    """Stand-in for asyncio.subprocess.Process.

    condor_q only touches communicate(), returncode, kill() and wait(), so those
    are all this needs to implement. `delay` lets a test push communicate() past
    the wait_for timeout.
    """

    def __init__(self, stdout=b"", stderr=b"", returncode=0, delay=0.0):
        self.stdout_data = stdout
        self.stderr_data = stderr
        self.returncode = returncode
        self.delay = delay
        self.killed = False
        self.reaped = False

    async def communicate(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.stdout_data, self.stderr_data

    def kill(self):
        self.killed = True

    async def wait(self):
        self.reaped = True
        return self.returncode


@pytest.fixture
def fake_schedd(monkeypatch):
    """Replace create_subprocess_exec with a fake, recording how it was called.

    Returns a callable: fake_schedd(proc) -> calls list, where each entry is
    {"argv": [...], "kwargs": {...}}.
    """

    calls = []

    def _install(proc: FakeProc) -> list:
        async def fake_exec(*argv, **kwargs):
            calls.append({"argv": list(argv), "kwargs": kwargs})
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        return calls

    return _install


def _run(proc, fake_schedd, **kwargs):
    """Install `proc` as the schedd and run one condor_q call."""

    calls = fake_schedd(proc)
    result = asyncio.run(condor_q("true", ["Owner"], **kwargs))
    return result, calls


def _json_out(ads) -> bytes:
    return json.dumps(ads).encode()


class TestCondorQKeys:

    def test_keys_are_cluster_dot_proc(self, fake_schedd):
        out = _json_out([
            {"ClusterId": 12, "ProcId": 0, "Owner": "alice"},
            {"ClusterId": 12, "ProcId": 1, "Owner": "alice"},
        ])

        jobs, _ = _run(FakeProc(stdout=out), fake_schedd)

        assert set(jobs) == {"12.0", "12.1"}
        assert jobs["12.1"]["ProcId"] == 1

    def test_missing_proc_id_defaults_to_zero(self, fake_schedd):
        out = _json_out([{"ClusterId": 34, "Owner": "bob"}])

        jobs, _ = _run(FakeProc(stdout=out), fake_schedd)

        assert set(jobs) == {"34.0"}

    def test_missing_cluster_id_falls_back_to_positional_key(self, fake_schedd):
        out = _json_out([
            {"ClusterId": 5, "ProcId": 0},
            {"Owner": "no-cluster-here"},
        ])

        jobs, _ = _run(FakeProc(stdout=out), fake_schedd)

        assert set(jobs) == {"5.0", "unknown.1"}

    def test_duplicate_job_ids_collapse_and_warn(self, fake_schedd, caplog):
        out = _json_out([
            {"ClusterId": 7, "ProcId": 0, "Owner": "first"},
            {"ClusterId": 7, "ProcId": 0, "Owner": "second"},
        ])

        with caplog.at_level("WARNING", logger=htcondor_cli.__name__):
            jobs, _ = _run(FakeProc(stdout=out), fake_schedd)

        assert set(jobs) == {"7.0"}
        assert jobs["7.0"]["Owner"] == "second", "last ad should win"
        assert any("unique job keys" in r.getMessage() for r in caplog.records)


class TestCondorQInterning:

    def test_repeated_values_share_one_object(self, fake_schedd):
        # json.loads does not memoize string *values*, so identity across two ads
        # is only possible if condor_q interned them.
        out = _json_out([
            {"ClusterId": 1, "ProcId": 0, "Owner": "a-repeated-owner-value"},
            {"ClusterId": 1, "ProcId": 1, "Owner": "a-repeated-owner-value"},
        ])

        jobs, _ = _run(FakeProc(stdout=out), fake_schedd)

        assert jobs["1.0"]["Owner"] is jobs["1.1"]["Owner"]
        assert jobs["1.0"]["Owner"] is sys.intern("a-repeated-owner-value")

    def test_interns_nested_dicts_and_lists(self, fake_schedd):
        out = _json_out([{
            "ClusterId": 2,
            "ProcId": 0,
            "Args": ["a-nested-list-value", "a-nested-list-value"],
            "Extra": {"a-nested-dict-key": "a-nested-dict-value"},
        }])

        jobs, _ = _run(FakeProc(stdout=out), fake_schedd)

        ad = jobs["2.0"]
        assert ad["Args"][0] is ad["Args"][1]
        assert ad["Args"][0] is sys.intern("a-nested-list-value")
        assert ad["Extra"]["a-nested-dict-key"] is sys.intern("a-nested-dict-value")

    def test_non_string_values_pass_through_unchanged(self, fake_schedd):
        out = _json_out([{
            "ClusterId": 3,
            "ProcId": 0,
            "JobStatus": 2,
            "RequestMemory": 1.5,
            "Held": False,
            "Nothing": None,
        }])

        jobs, _ = _run(FakeProc(stdout=out), fake_schedd)

        ad = jobs["3.0"]
        assert ad["JobStatus"] == 2
        assert ad["RequestMemory"] == 1.5
        assert ad["Held"] is False
        assert ad["Nothing"] is None


class TestYesterday:

    def test_spans_one_local_day(self):
        start, end = htcondor_cli.yesterday()

        assert end - start == timedelta(days=1)

    def test_edges_are_midnight(self):
        start, end = htcondor_cli.yesterday()

        for edge in (start, end):
            assert (edge.hour, edge.minute, edge.second, edge.microsecond) == (0, 0, 0, 0)

    def test_ends_at_todays_midnight(self):
        _, end = htcondor_cli.yesterday()

        assert end.date() == datetime.now().date()


class TestWindowConstraint:

    def test_is_half_open_on_qdate_epochs(self):
        start = datetime(2026, 8, 3)
        end = datetime(2026, 8, 4)

        assert htcondor_cli.window_constraint(start, end) == (
            f"QDate >= {int(start.timestamp())} && QDate < {int(end.timestamp())}"
        )

    def test_empty_window_is_rejected(self):
        day = datetime(2026, 8, 3)

        with pytest.raises(ValueError, match="must be after start"):
            htcondor_cli.window_constraint(day, day)

    def test_backwards_window_is_rejected(self):
        with pytest.raises(ValueError, match="must be after start"):
            htcondor_cli.window_constraint(datetime(2026, 8, 4), datetime(2026, 8, 3))


class TestCondorQWindow:

    def test_window_is_applied_with_no_arguments(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q())

        start, end = htcondor_cli.yesterday()
        argv = calls[0]["argv"]

        assert argv[argv.index("-constraint") + 1] == htcondor_cli.window_constraint(start, end)

    def test_explicit_start_and_end_are_used(self, fake_schedd):
        start = datetime(2026, 7, 1, 12)
        end = datetime(2026, 7, 2, 12)

        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q(start=start, end=end))

        argv = calls[0]["argv"]

        assert argv[argv.index("-constraint") + 1] == htcondor_cli.window_constraint(start, end)

    def test_start_alone_keeps_the_default_end(self, fake_schedd):
        start = datetime(2026, 7, 1)
        _, default_end = htcondor_cli.yesterday()

        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q(start=start))

        argv = calls[0]["argv"]

        assert argv[argv.index("-constraint") + 1] == htcondor_cli.window_constraint(start, default_end)

    def test_end_alone_keeps_the_default_start(self, fake_schedd):
        default_start, _ = htcondor_cli.yesterday()
        end = datetime.now() + timedelta(days=1)

        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q(end=end))

        argv = calls[0]["argv"]

        assert argv[argv.index("-constraint") + 1] == htcondor_cli.window_constraint(default_start, end)

    def test_caller_constraint_is_anded_onto_the_window(self, fake_schedd):
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 2)

        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("JobStatus == 1", start=start, end=end))

        argv = calls[0]["argv"]

        assert argv[argv.index("-constraint") + 1] == (
            f"({htcondor_cli.window_constraint(start, end)}) && (JobStatus == 1)"
        )

    def test_caller_constraint_cannot_replace_the_window(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("true"))

        constraint = calls[0]["argv"][calls[0]["argv"].index("-constraint") + 1]

        assert "QDate >=" in constraint, "the window must survive a caller constraint"

    def test_compound_caller_constraint_is_parenthesized(self, fake_schedd):
        """Without the parens, a top-level || would escape the window."""

        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("JobStatus == 1 || JobStatus == 2"))

        constraint = calls[0]["argv"][calls[0]["argv"].index("-constraint") + 1]

        assert constraint.endswith("&& (JobStatus == 1 || JobStatus == 2)")

    def test_empty_explicit_window_raises_before_spawning(self, fake_schedd):
        day = datetime(2026, 8, 3)
        calls = fake_schedd(FakeProc(stdout=b"[]"))

        with pytest.raises(ValueError):
            asyncio.run(condor_q(start=day, end=day))

        assert calls == [], "condor_q should not be spawned for an empty window"


class TestCondorQArgv:

    def test_key_attrs_are_always_requested_first(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("Owner == \"alice\"", ["Owner", "JobStatus"]))

        argv = calls[0]["argv"]
        attrs = argv[argv.index("-attributes") + 1]

        assert attrs == "ClusterId,ProcId,Owner,JobStatus"

    def test_requested_attrs_are_deduped_preserving_order(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("true", ["Owner", "ClusterId", "Owner", "JobStatus"]))

        argv = calls[0]["argv"]
        attrs = argv[argv.index("-attributes") + 1]

        assert attrs == "ClusterId,ProcId,Owner,JobStatus"

    def test_limit_is_stringified(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("JobStatus == 1", ["Owner"], limit=37))

        argv = calls[0]["argv"]

        assert argv[0] == htcondor_cli.CONDOR_Q
        assert "-json" in argv
        assert argv[argv.index("-limit") + 1] == "37", "limit must be stringified for argv"

    def test_attrs_default_to_the_key_attrs_alone(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q())

        argv = calls[0]["argv"]

        assert argv[argv.index("-attributes") + 1] == "ClusterId,ProcId"

    def test_pool_is_omitted_by_default(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("true", ["Owner"]))

        assert "-pool" not in calls[0]["argv"], "no -pool means query the local pool"

    def test_pool_is_passed_when_given(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("true", ["Owner"], pool="cm.chtc.wisc.edu"))

        argv = calls[0]["argv"]

        assert argv[argv.index("-pool") + 1] == "cm.chtc.wisc.edu"

    def test_allusers_is_omitted_by_default(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("true", ["Owner"]))

        assert "-allusers" not in calls[0]["argv"]

    def test_allusers_flag_is_added_when_requested(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("true", ["Owner"], all_users=True))

        argv = calls[0]["argv"]

        assert "-allusers" in argv
        assert argv[argv.index("-allusers") + 1] == "-constraint", "-allusers takes no value"

    def test_pool_and_allusers_precede_the_query_options(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("true", ["Owner"], pool="cm.chtc.wisc.edu", all_users=True))

        argv = calls[0]["argv"]

        assert argv[:5] == [htcondor_cli.CONDOR_Q, "-json", "-pool", "cm.chtc.wisc.edu", "-allusers"]

    def test_global_and_name_are_omitted_by_default(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q())

        argv = calls[0]["argv"]

        assert "-global" not in argv, "the local schedd answers by default"
        assert "-name" not in argv

    def test_global_flag_is_added_when_requested(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q(global_=True))

        argv = calls[0]["argv"]

        assert "-global" in argv
        assert argv[argv.index("-global") + 1] == "-constraint", "-global takes no value"

    def test_name_is_passed_when_given(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q(name="ap2001.chtc.wisc.edu"))

        argv = calls[0]["argv"]

        assert argv[argv.index("-name") + 1] == "ap2001.chtc.wisc.edu"

    def test_pool_composes_with_global(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q(pool="cm.chtc.wisc.edu", global_=True))

        argv = calls[0]["argv"]

        assert argv[:5] == [htcondor_cli.CONDOR_Q, "-json", "-pool", "cm.chtc.wisc.edu", "-global"]

    def test_pool_composes_with_name(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q(pool="cm.chtc.wisc.edu", name="ap2001.chtc.wisc.edu"))

        argv = calls[0]["argv"]

        assert argv[:6] == [htcondor_cli.CONDOR_Q, "-json", "-pool", "cm.chtc.wisc.edu",
                            "-name", "ap2001.chtc.wisc.edu"]

    def test_global_and_name_together_are_rejected(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))

        with pytest.raises(ValueError, match="cannot be combined with name"):
            asyncio.run(condor_q(global_=True, name="ap2001.chtc.wisc.edu"))

        assert calls == [], "condor_q should not be spawned for a contradictory target"

    def test_runs_with_a_scrubbed_environment(self, fake_schedd):
        calls = fake_schedd(FakeProc(stdout=b"[]"))
        asyncio.run(condor_q("true", ["Owner"]))

        env = calls[0]["kwargs"]["env"]

        assert env["PATH"] == "/usr/bin:/bin"
        assert "CONDOR_CONFIG" in env
        assert "HOME" not in env, "the child should not inherit the caller's environment"


class TestCondorQEmptyOutput:

    def test_no_output_returns_empty_dict(self, fake_schedd):
        jobs, _ = _run(FakeProc(stdout=b""), fake_schedd)

        assert jobs == {}

    def test_whitespace_only_output_returns_empty_dict(self, fake_schedd):
        jobs, _ = _run(FakeProc(stdout=b"  \n  "), fake_schedd)

        assert jobs == {}

    def test_empty_json_array_returns_empty_dict(self, fake_schedd):
        jobs, _ = _run(FakeProc(stdout=b"[]"), fake_schedd)

        assert jobs == {}


class TestCondorQErrors:

    def test_nonzero_exit_raises_schedd_error_with_stderr(self, fake_schedd):
        proc = FakeProc(stdout=b"", stderr=b"  Failed to fetch ads\n", returncode=1)

        with pytest.raises(ScheddError) as exc_info:
            _run(proc, fake_schedd)

        assert str(exc_info.value) == "Failed to fetch ads"

    def test_stderr_is_truncated(self, fake_schedd):
        proc = FakeProc(stderr=b"x" * 5000, returncode=1)

        with pytest.raises(ScheddError) as exc_info:
            _run(proc, fake_schedd)

        assert len(str(exc_info.value)) == 500

    def test_undecodable_stderr_does_not_mask_the_error(self, fake_schedd):
        proc = FakeProc(stderr=b"bad byte: \xff", returncode=1)

        with pytest.raises(ScheddError) as exc_info:
            _run(proc, fake_schedd)

        assert "bad byte" in str(exc_info.value)

    def test_unparseable_output_raises_schedd_error(self, fake_schedd):
        with pytest.raises(ScheddError, match="could not parse condor_q output"):
            _run(FakeProc(stdout=b"not json at all"), fake_schedd)

    def test_timeout_raises_schedd_timeout(self, fake_schedd):
        proc = FakeProc(stdout=b"[]", delay=10)

        with pytest.raises(ScheddTimeout, match="exceeded 0.05s"):
            _run(proc, fake_schedd, timeout=0.05)

    def test_timeout_kills_and_reaps_the_child(self, fake_schedd):
        proc = FakeProc(stdout=b"[]", delay=10)

        with pytest.raises(ScheddTimeout):
            _run(proc, fake_schedd, timeout=0.05)

        assert proc.killed, "the child must be killed on timeout"
        assert proc.reaped, "the killed child must be awaited or it leaks"

    def test_semaphore_is_released_after_a_timeout(self, fake_schedd):
        """A timeout must not permanently consume a schedd slot."""

        slow = FakeProc(stdout=b"[]", delay=10)
        fast = FakeProc(stdout=_json_out([{"ClusterId": 9, "ProcId": 0}]))

        async def scenario():
            # Burn every schedd slot on a timeout, then check one more call still
            # gets through. _value is the semaphore's remaining capacity.
            for _ in range(htcondor_cli._SCHEDD_SEM._value):
                fake_schedd(slow)
                with pytest.raises(ScheddTimeout):
                    await condor_q("true", ["Owner"], timeout=0.01)

            fake_schedd(fast)
            # Bounded so a leaked slot fails the test instead of hanging it.
            return await asyncio.wait_for(condor_q("true", ["Owner"]), timeout=5)

        assert set(asyncio.run(scenario())) == {"9.0"}
