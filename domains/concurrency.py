"""Master + N workers + M async runners — concurrency layer for the substrate.

Architecture intent (matches the converged biology research: Baars'
Global Workspace, Posner & Petersen's executive attention, ACT-R's
central production system, Friston's multi-timescale prediction):

* The **master thread** is the only writer to the live ``mind_graph``.
  Same posture as Baars' global workspace bottleneck — a single
  sequential "spotlight" of access.

* **N supporting threads** run as a `WorkerPool`. Each worker
  receives a `Task`, computes in **isolation** (its own scratch
  substrate or just pure computation), and returns a `Result` whose
  ``apply`` field is a closure ``apply(agent)`` the master will run
  on its own thread. Matches ACT-R modules — parallel processing,
  serial commit. Real CPU parallelism via Rust GIL release on the
  substrate's hot paths.

* **M async runners** run on a single dedicated OS thread with an
  asyncio event loop, capped at M concurrent coroutines. The natural
  home for I/O work (teacher calls, HTTP, file ops) and for
  long-period background processes (memory consolidation, hormonal
  drives). Doesn't compete with workers for CPU.

* Both surfaces deliver `Result` objects to a shared queue the master
  drains in `master_tick`. Result.apply is the only path back into
  the live graph — preserving Π as the only mutation door.

Thread/process boundary:
  * Workers use Python `threading.Thread` (shared memory). The Rust
    substrate is `unsendable` at the PyO3 layer so a worker that
    needs substrate access must operate on a snapshot or a scratch
    substrate of its own.
  * Async runners run a single event loop on one OS thread; the M
    concurrent coroutines share that thread (asyncio.Semaphore caps).
  * Mutations land on the master's thread, deterministically, in the
    order results are drained.

Failure model:
  * A worker that raises catches the exception in its loop and
    delivers a `Result(error=exc, apply=None)`. The pool keeps
    running. Same shape as the master's "init reaping zombies" pattern
    for cooperative threads.
  * `apply` callables that raise on the master's thread propagate up
    — they're the caller's bug, not the pool's.

This module has no dependency on `substrate_rs` or `CuriousAgent` —
it's a standalone primitive layer. The integration glue lives next to
the agent code that uses it.
"""
from __future__ import annotations

import asyncio
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


# A worker's payload is anything serialisable across the thread
# boundary — primitives, dicts, dataclasses. NOT a substrate handle
# (the Rust substrate isn't safely shareable across threads).
Payload = Any

# A `Task` callable runs in a worker thread; the value it returns
# becomes Result.value. If the value is itself a 1-argument callable
# (signature `apply(agent) -> None`), it lands as Result.apply
# instead — that's the master-commit path. This dual return shape
# lets simple workers ("compute and return a number") and graph-
# mutating workers ("compute and commit these changes") share one API.
TaskFn = Callable[[Payload], Any]
AsyncTaskFn = Callable[[Payload], Awaitable[Any]]
ApplyFn = Callable[[Any], None]


@dataclass
class Result:
    """Outcome of one task. The master drains a queue of these per tick.

    ``apply`` is the mutation closure to run on the master's thread —
    None if the task returned a plain value (recorded in ``value``).
    ``error`` carries any exception raised during the task; pool keeps
    running.
    """
    task_id: int
    pool: str = ""
    apply: Optional[ApplyFn] = None
    value: Any = None
    error: Optional[BaseException] = None
    wall_ms: float = 0.0

    def ok(self) -> bool:
        return self.error is None


def _classify_return(rv: Any) -> tuple[Optional[ApplyFn], Any]:
    """Split a task's return value into (apply_closure, plain_value).

    A 1-arg callable that isn't a class is treated as the commit
    closure — `apply(agent)`. Everything else is a plain value.

    The class check guards against `RandomClass(agent)` accidentally
    being treated as a commit closure; in practice workers return
    closures or scalars / tuples / dicts.
    """
    if callable(rv) and not isinstance(rv, type):
        return rv, None
    return None, rv


# --- Worker pool (N OS threads) ----------------------------------------

class WorkerPool:
    """N OS-thread workers pulling Task callables off a queue.

    Submit `(fn, payload)` via `submit`; drain completed Results via
    `drain`. The master is the sole consumer of `drain` — calling it
    from any other thread is racy with the master's apply path.

    Pool lifecycle: workers are daemon threads, so they don't keep
    the process alive on shutdown; explicit `stop()` is still the
    clean path (sends poison pills, joins).
    """

    def __init__(self, n_workers: int = 4, name: str = "default"):
        if n_workers < 1:
            raise ValueError("n_workers must be ≥ 1")
        self.name = name
        self.n_workers = n_workers
        self._inq: queue.Queue = queue.Queue()
        self._outq: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._next_id = 0
        self._id_lock = threading.Lock()
        self._workers = [
            threading.Thread(
                target=self._loop,
                daemon=True,
                name=f"worker:{name}:{i}",
            )
            for i in range(n_workers)
        ]
        for w in self._workers:
            w.start()

    def submit(self, fn: TaskFn, payload: Payload = None) -> int:
        """Schedule `(fn, payload)` for execution on the next free
        worker. Returns the task id — the same id lands in
        Result.task_id when it completes."""
        with self._id_lock:
            tid = self._next_id
            self._next_id += 1
        self._inq.put((tid, fn, payload))
        return tid

    def drain(self, limit: int = 64) -> list[Result]:
        """Pop up to `limit` completed Results, non-blocking. Called
        by the master per tick. `limit` keeps a flood of results from
        starving the master's other work — 64 is generous for typical
        per-tick rates."""
        out: list[Result] = []
        for _ in range(limit):
            try:
                out.append(self._outq.get_nowait())
            except queue.Empty:
                break
        return out

    def pending(self) -> int:
        """Approximate count of tasks in-flight (queued + currently
        executing). Useful for back-pressure decisions."""
        return self._inq.qsize() + self._outq.qsize()

    def stop(self, join_timeout: float = 1.0) -> None:
        """Stop the pool. Sends one poison pill per worker; joins
        with `join_timeout` per worker (daemon threads die on process
        exit regardless)."""
        self._stop.set()
        for _ in self._workers:
            self._inq.put((-1, None, None))  # poison pill
        for w in self._workers:
            w.join(timeout=join_timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                tid, fn, payload = self._inq.get(timeout=0.25)
            except queue.Empty:
                continue
            if tid == -1:
                return
            t0 = time.perf_counter()
            try:
                rv = fn(payload)
                apply, value = _classify_return(rv)
                self._outq.put(Result(
                    task_id=tid, pool=self.name,
                    apply=apply, value=value,
                    wall_ms=(time.perf_counter() - t0) * 1000.0,
                ))
            except BaseException as e:
                self._outq.put(Result(
                    task_id=tid, pool=self.name,
                    error=e,
                    wall_ms=(time.perf_counter() - t0) * 1000.0,
                ))


# --- Async runner (M concurrent coroutines on a dedicated thread) -------

class AsyncRunner:
    """asyncio event loop on a dedicated OS thread, capped at M
    concurrent coroutines via a semaphore.

    Natural home for I/O work (teacher calls, HTTP, file work) and for
    long-period background processes (memory consolidation,
    hormonal-shape drives). Submitted tasks compete only with each
    other for the runner's single thread — they don't compete with
    workers for CPU.

    `submit(coro_fn, payload)` runs `await coro_fn(payload)`. The
    return-value classification (callable → apply, otherwise → value)
    matches `WorkerPool`.
    """

    def __init__(self, max_concurrent: int = 16, name: str = "default"):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be ≥ 1")
        self.name = name
        self.max_concurrent = max_concurrent
        self._outq: queue.Queue = queue.Queue()
        self._next_id = 0
        self._id_lock = threading.Lock()
        self._started = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sem: Optional[asyncio.Semaphore] = None
        # Do not depend on ``loop.call_soon_threadsafe`` for submission.
        # Some supported runtimes can start a selector loop on a background
        # thread but fail to wake its self-pipe from another thread.  A plain
        # Queue plus a short loop-owned poll keeps all asyncio operations on
        # the runner thread and has the same single-writer shape as the graph.
        self._inq: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._scheduled: set[asyncio.Task] = set()
        self._pending_count = 0
        self._pending_lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name=f"async:{name}"
        )
        self._thread.start()
        # Block until the loop + semaphore are ready so submit() can't
        # race with construction.
        self._started.wait()

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._sem = asyncio.Semaphore(self.max_concurrent)
        self._loop.call_soon(self._pump_submissions)
        self._started.set()
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()

    def _pump_submissions(self) -> None:
        """Move cross-thread submissions onto the loop from its own thread."""
        assert self._loop is not None
        while True:
            try:
                tid, coro_fn, payload = self._inq.get_nowait()
            except queue.Empty:
                break
            task = self._loop.create_task(
                self._execute(tid, coro_fn, payload))
            self._scheduled.add(task)
            task.add_done_callback(self._scheduled.discard)

        if self._stop.is_set():
            for task in tuple(self._scheduled):
                task.cancel()
            self._loop.stop()
            return
        # This timer is also the wake source: the selector never sleeps
        # indefinitely waiting for a cross-thread self-pipe notification.
        self._loop.call_later(0.001, self._pump_submissions)

    async def _execute(
        self, tid: int, coro_fn: AsyncTaskFn, payload: Payload
    ) -> None:
        assert self._sem is not None
        t0 = time.perf_counter()
        try:
            async with self._sem:
                rv = await coro_fn(payload)
                apply, value = _classify_return(rv)
                self._outq.put(Result(
                    task_id=tid, pool=self.name,
                    apply=apply, value=value,
                    wall_ms=(time.perf_counter() - t0) * 1000.0,
                ))
        except BaseException as e:
            self._outq.put(Result(
                task_id=tid, pool=self.name,
                error=e,
                wall_ms=(time.perf_counter() - t0) * 1000.0,
            ))
        finally:
            with self._pending_lock:
                self._pending_count -= 1

    def submit(self, coro_fn: AsyncTaskFn, payload: Payload = None) -> int:
        """Schedule `await coro_fn(payload)` onto the runner's loop.
        Returns the task id; Result lands in the drain queue when the
        coroutine completes (or raises)."""
        with self._id_lock:
            if self._stop.is_set():
                raise RuntimeError("cannot submit to a stopped AsyncRunner")
            tid = self._next_id
            self._next_id += 1
            with self._pending_lock:
                self._pending_count += 1
            self._inq.put((tid, coro_fn, payload))
        return tid

    def drain(self, limit: int = 64) -> list[Result]:
        """Same shape as `WorkerPool.drain`."""
        out: list[Result] = []
        for _ in range(limit):
            try:
                out.append(self._outq.get_nowait())
            except queue.Empty:
                break
        return out

    def pending(self) -> int:
        """Approximate number of submitted, in-flight, or buffered results."""
        with self._pending_lock:
            in_flight = self._pending_count
        return in_flight + self._outq.qsize()

    def stop(self, join_timeout: float = 1.0) -> None:
        """Stop the runner. The asyncio loop exits cleanly on the
        next iteration; outstanding coroutines may not get to push
        their result."""
        # Serialise shutdown with submit(), so no item can enter the queue
        # after the loop has observed the stop flag.
        with self._id_lock:
            self._stop.set()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=join_timeout)


# --- Memory consolidation runner (CLS-shaped background) ----------------

class MemoryConsolidationRunner:
    """A periodic background process running on top of an `AsyncRunner`.

    Models the CLS (Complementary Learning Systems — McClelland 1995;
    Kumaran 2016) shape: hippocampus fast-system fires per-event, then
    a slower offline replay consolidates into neocortex. Here the
    "consolidate" coroutine fires every `period_s` seconds, takes
    whatever pending memory work the user supplies via the
    `consolidate_fn`, and produces an `apply(agent)` closure the
    master commits on its own thread.

    Doesn't know anything about the agent or the substrate — the
    caller supplies the consolidation function. That keeps this
    primitive composable: a different substrate or a different memory
    architecture plugs in the same way.

    CONSTRAINT (load-bearing): `consolidate_fn` runs on the async
    runner's thread; it MUST NOT touch the substrate directly. The
    Rust `substrate_rs.Substrate` is unsendable and cross-thread
    access will panic. Return an `apply(agent)` closure that does all
    the substrate work — the master will run it on its own thread.
    This split (schedule on background, commit on master) is exactly
    the bio-faithful posture: parallel timing, serial commit.
    """

    def __init__(
        self,
        runner: AsyncRunner,
        consolidate_fn: Callable[[], ApplyFn | None],
        period_s: float = 5.0,
        name: str = "memory_consolidation",
    ):
        self.runner = runner
        self.consolidate_fn = consolidate_fn
        self.period_s = period_s
        self.name = name
        self._stop = threading.Event()
        self._submitted_ids: list[int] = []

    async def _periodic(self, _payload: Payload) -> Optional[ApplyFn]:
        """One consolidation pass. Returns an apply-closure for the
        master, or None if there was nothing to consolidate."""
        while not self._stop.is_set():
            await asyncio.sleep(self.period_s)
            apply = self.consolidate_fn()
            if apply is not None:
                # Returning here surfaces this apply to the master.
                # Then we self-resubmit so consolidation keeps running.
                self._submit_next()
                return apply
        return None

    def _submit_next(self) -> None:
        tid = self.runner.submit(self._periodic, payload=None)
        self._submitted_ids.append(tid)

    def start(self) -> None:
        """Begin the periodic consolidation cycle."""
        self._submit_next()

    def stop(self) -> None:
        """Stop the periodic cycle. Already-pending coroutines run to
        completion (or to their next `asyncio.sleep` boundary)."""
        self._stop.set()


# --- Orchestrator: ties drain calls together ----------------------------

class ConcurrencyLayer:
    """One-stop owner of pools + runners. The master calls `tick(agent)`
    each master_tick; the layer drains every pool and runner and
    applies each result's `apply(agent)` closure on the master's
    thread.

    Keeps the master loop tiny. The agent's `master_tick` just adds:

        layer.tick(agent)

    after fire_reflexes + tick_threads. Result `value`s and errors
    accumulate on the layer's `recent_results` deque for inspection.
    """

    def __init__(self, max_results_per_tick: int = 64, history: int = 256):
        self.pools: list[WorkerPool] = []
        self.runners: list[AsyncRunner] = []
        self.max_results_per_tick = max_results_per_tick
        self.history = history
        self.recent_results: list[Result] = []

    def add_pool(self, pool: WorkerPool) -> WorkerPool:
        self.pools.append(pool)
        return pool

    def add_runner(self, runner: AsyncRunner) -> AsyncRunner:
        self.runners.append(runner)
        return runner

    def tick(self, agent: Any) -> dict:
        """Drain every pool + runner; apply each result's apply
        closure on the caller's thread (the master).

        Returns a small dict for inspection: how many results
        applied, errored, or ignored.
        """
        applied = 0
        errored = 0
        ignored = 0
        for src in (*self.pools, *self.runners):
            for r in src.drain(self.max_results_per_tick):
                self._record(r)
                if r.error is not None:
                    errored += 1
                    continue
                if r.apply is not None:
                    r.apply(agent)
                    applied += 1
                else:
                    ignored += 1
        return {"applied": applied, "errored": errored, "ignored": ignored}

    def _record(self, r: Result) -> None:
        self.recent_results.append(r)
        if len(self.recent_results) > self.history:
            self.recent_results = self.recent_results[-self.history:]

    def stop_all(self) -> None:
        for p in self.pools:
            p.stop()
        for r in self.runners:
            r.stop()
