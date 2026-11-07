"""Phase 055: concurrent decisions, the shared call budget under threads, and the call cap in a pooled town.

The sequential baseline is the same game with each LLM backend's ``concurrent`` flag turned off, which is the
original path in ``BigvilleGame.step()``."""
from __future__ import annotations

import threading
import time

import pytest

from bigville.backends.autopilot import CallBudget
from bigville.concurrency import decide_pooled, pool_workers
from bigville.llm_scenario import RunDigest, build_llm_town
from bigville.llm_transcript import prompt_hash
from llm_stub import FakeProvider

from llm_stub import varied_reply


def _calls(provider):
    return sorted((call["meta"]["turn"], call["meta"]["actor"], prompt_hash(call["payload"]))
                  for call in provider.calls)


def _run(game, turns):
    digest = RunDigest()
    for _ in range(turns):
        assert game.step()["status"] == "advanced"
        digest.add(game)
    return digest.hexdigest()


def test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical():
    turns = 2
    sequential_provider = FakeProvider(varied_reply, delay=0.3)
    sequential = build_llm_town(sequential_provider, llm_residents=8, concurrency=4, llm_log=False)
    for backend in (sequential.backends[name] for name in sequential.llm_residents):
        backend.concurrent = False
    started = time.perf_counter()
    sequential_digest = _run(sequential, turns)
    sequential_seconds = time.perf_counter() - started

    concurrent_provider = FakeProvider(varied_reply, delay=0.3)
    concurrent = build_llm_town(concurrent_provider, llm_residents=8, concurrency=4, llm_log=False)
    started = time.perf_counter()
    concurrent_digest = _run(concurrent, turns)
    concurrent_seconds = time.perf_counter() - started

    assert concurrent_digest == sequential_digest
    assert _calls(concurrent_provider) == _calls(sequential_provider)
    # Consults are gated by the autopilot, so not every resident is asked every turn.
    assert 0 < len(concurrent_provider.calls) <= 8 * turns
    print(f"\nSPEEDUP sequential={sequential_seconds:.2f}s concurrent={concurrent_seconds:.2f}s "
          f"ratio={concurrent_seconds / sequential_seconds:.2f} calls={len(concurrent_provider.calls)}")
    assert concurrent_seconds < 0.75 * sequential_seconds, (sequential_seconds, concurrent_seconds)


def test_the_pool_never_runs_more_decisions_at_once_than_its_size():
    class Counting(FakeProvider):
        def __init__(self):
            super().__init__(varied_reply, delay=0.05)
            self.active = 0
            self.most = 0
            self._count = threading.Lock()

        def complete(self, payload, meta=None):
            with self._count:
                self.active += 1
                self.most = max(self.most, self.active)
            try:
                return super().complete(payload, meta)
            finally:
                with self._count:
                    self.active -= 1

    provider = Counting()
    game = build_llm_town(provider, llm_residents=8, concurrency=2, llm_log=False)
    _run(game, 1)
    assert 1 <= provider.most <= 2


def test_decide_pooled_returns_in_registration_order_and_raises_the_first_failure():
    class Backend:
        concurrency = 3

        def __init__(self, delay, fail=None):
            self.delay, self.fail = delay, fail

        def decide(self, context):
            time.sleep(self.delay)
            if self.fail:
                raise self.fail
            return context

    slow_first = {"Ada": (Backend(0.2), "a"), "Ben": (Backend(0.0), "b"), "Cy": (Backend(0.1), "c")}
    assert list(decide_pooled(slow_first)) == ["Ada", "Ben", "Cy"]
    assert decide_pooled(slow_first) == {"Ada": "a", "Ben": "b", "Cy": "c"}
    assert decide_pooled({}) == {}
    assert pool_workers([Backend(0), Backend(0)]) == 3
    failing = {"Ada": (Backend(0.0), "a"), "Ben": (Backend(0.0, ValueError("bad")), "b")}
    with pytest.raises(ValueError, match="bad"):
        decide_pooled(failing)


def test_a_shared_call_budget_admits_exactly_its_cap_when_many_threads_ask_at_once():
    budget = CallBudget(max_calls_per_day=10)
    admitted = []
    lock = threading.Lock()
    barrier = threading.Barrier(64)

    def ask():
        barrier.wait()
        cause = budget.reserve("Ada", 0)
        with lock:
            admitted.append(cause)

    threads = [threading.Thread(target=ask) for _ in range(64)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert admitted.count(None) == 10
    assert admitted.count("call_cap") == 54


def test_a_spend_cap_is_checked_before_each_call_and_can_overshoot_by_the_calls_in_flight():
    cost, cap, workers = 0.002, 0.01, 4
    provider = FakeProvider(varied_reply, delay=0.05, cost=cost)
    game = build_llm_town(provider, llm_residents=8, concurrency=workers, budget=CallBudget(max_spend=cap),
                          llm_log=False)
    _run(game, 3)
    # A call is refused once the recorded spend reaches the cap. Calls already in flight were admitted before
    # their cost was recorded, so at most workers - 1 extra calls can start after the cap is reached.
    calls_allowed = int(cap / cost) + workers - 1
    assert len(provider.calls) <= calls_allowed
    assert len(provider.calls) >= int(cap / cost)


def test_a_call_cap_in_a_pooled_town_yields_the_autopilot_not_a_failure():
    provider = FakeProvider(varied_reply)
    game = build_llm_town(provider, llm_residents=4, budget=CallBudget(max_calls_per_day=1), llm_log=False)
    _run(game, 4)
    capped = [name for name in game.llm_residents
              if game.backends[name].llm_counts["fallbacks_by_cause"]["call_cap"] > 0]
    assert capped, "with one call per day, later consults must be refused"
    for name in capped:
        counts = game.backends[name].llm_counts
        assert counts["fallbacks_by_cause"]["provider_error"] == 0
        assert counts["calls"] == 1
        assert counts["autopilot_turns"] + counts["failures"] + counts["successes"] >= 1
    assert game.last_errors == {}
