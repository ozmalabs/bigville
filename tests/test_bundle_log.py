"""DR02: append-only bundle journal, replay and verification.

The pure tests use synthetic bundles/results/acks; the integration test uses the
same small three-actor scenario as ``test_bundle_dispatch.py`` so a real
partitioned turn can be replayed and compared with ``last_bundle_log``.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import CheapBackend
from bigville.bundle_checks import (TickBundleLog, bundle_execution_sha,
                                    bundle_output_sha)
from bigville.bundle_log import (BundleJournal, BundleJournalError,
                                 DuplicateRecordError, JournalCorruptionError,
                                 JournalPathError, JournalTruncatedError,
                                 JournalVerifyError)
from bigville.bundles import (Bundle, BundleAck, BundleOperation, BundleResult,
                              ExecutionNamespace, QualifiedId, canonical_json)
from worlds.tick_graph import Resource


RUN = "run1"
BASE = 3
ACTOR = Resource("actor", "Ada")
CELL = Resource("cell", (1, 2))
WITNESS = Resource("witness", (1, 2))


def _bundle(seq: int, *, shard: int | None = None) -> Bundle:
    namespace = ExecutionNamespace(
        run_id=RUN, executor="partitioned",
        shard=seq + 1 if shard is None else shard,
        tick=BASE, bundle_seq=seq)
    operation = BundleOperation(
        op_id=f"op{seq}", actor="Ada", kind="move",
        params={"seq": seq}, reads=(ACTOR,), writes=(CELL,),
        tiebreak=(seq, "Ada"))
    return Bundle(
        bundle_id=namespace.name,
        namespace=namespace,
        run_id=RUN,
        tick=BASE,
        shard=namespace.shard,
        base_version=BASE,
        operations=(operation,),
        reads=(ACTOR, CELL),
        writes=(CELL, WITNESS),
        tiebreak=(seq, "Ada"),
    )


def _result(bundle: Bundle) -> BundleResult:
    draft = BundleResult(
        bundle_id=bundle.bundle_id,
        namespace=bundle.namespace,
        base_version=bundle.base_version,
        status="ok",
        effects=({"op": "move", "seq": bundle.namespace.bundle_seq},),
        created_ids=(QualifiedId(bundle.namespace.name, 100),),
        result=(("Ada", True, None),),
        output_sha="pending",
        execution_sha="pending",
        reason="",
    )
    draft = replace(draft, output_sha=bundle_output_sha(draft))
    return replace(draft, execution_sha=bundle_execution_sha(bundle, draft))


def _ack(bundle: Bundle, result: BundleResult,
         committed_version: int) -> BundleAck:
    return BundleAck(
        bundle_id=bundle.bundle_id,
        base_version=bundle.base_version,
        outcome="committed",
        committed_version=committed_version,
        execution_sha=result.execution_sha,
    )


def _write_tick(journal: BundleJournal, bundles: list[Bundle], *,
                committed_versions: list[int] | None = None,
                payload: dict | None = None,
                revision: int | None = None) -> TickBundleLog:
    """Write one complete synthetic tick and return its in-memory log."""
    versions = committed_versions or [BASE + 1 + index
                                      for index in range(len(bundles))]
    assert len(versions) == len(bundles)
    log = TickBundleLog(RUN, BASE)
    journal.tick_start(RUN, BASE, base_version=BASE, revision=BASE)
    for bundle in bundles:
        log.dispatch(bundle)
        journal.dispatch(bundle)
    for bundle, committed in zip(bundles, versions):
        result = _result(bundle)
        log.result(result)
        journal.result(result)
        ack = _ack(bundle, result, committed)
        log.acknowledge(ack)
        journal.ack(ack)
        log.commit(bundle.bundle_id)
        journal.commit(bundle.bundle_id, committed)
    payload_sha = log.payload_sha({} if payload is None else payload)
    journal.tick_end(
        BASE,
        execution_sha=log.execution_sha,
        payload_sha=payload_sha,
        revision=max(versions + [BASE]) if revision is None else revision,
        run_id=RUN,
    )
    return log


def _complete_records(tmp_path: Path) -> list[dict]:
    path = tmp_path / "source.jsonl"
    with BundleJournal(path) as journal:
        _write_tick(journal, [_bundle(0), _bundle(1)])
    return list(BundleJournal(path).read())


def _write_records(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical_json(record) + "\n"
                            for record in records), encoding="utf-8")
    return path


# ------------------------------------------------------------------ round trip


def test_round_trip_read_replay_verify(tmp_path):
    path = tmp_path / "nested" / "journal.jsonl"
    bundles = [_bundle(0), _bundle(1)]
    with BundleJournal(path) as journal:
        original = _write_tick(journal, bundles, payload={"world": "state"})

    assert path.is_file()
    reader = BundleJournal(path)
    records = list(reader.read())
    assert [record["kind"] for record in records] == [
        "tick_start",
        "dispatch", "dispatch",
        "result", "ack", "commit",
        "result", "ack", "commit",
        "tick_end",
    ]
    assert reader.last_read_report is not None
    assert reader.last_read_report.truncated_tail is False
    assert reader.last_read_report.record_count == len(records)

    logs = reader.replay()
    assert len(logs) == 1
    replayed = logs[0]
    assert tuple(replayed.dispatched) == tuple(original.dispatched)
    assert replayed.results == original.results
    assert replayed.acks == original.acks
    assert replayed.committed_order == original.committed_order
    assert replayed.execution_sha == original.execution_sha
    assert replayed.payload_sha() == original.payload_sha()
    assert replayed.to_dict() == original.to_dict()

    report = reader.verify()
    assert report.records == len(records)
    assert report.ticks == 1
    assert report.aborted_ticks == 0
    assert report.bundles == 2
    assert report.revisions == (5,)
    assert report.truncated_tail is False

    # Every line is canonical JSON (compact, sorted keys).
    for line in path.read_text(encoding="utf-8").splitlines():
        assert line == canonical_json(json.loads(line))
    reader.close()


def test_two_identical_tick_versions_are_separate_blocks(tmp_path):
    # A no-mutation turn can reuse the same graph revision as its tick.  The
    # journal keys replay by record block, not by (run_id, tick) uniqueness.
    path = tmp_path / "journal.jsonl"
    with BundleJournal(path) as journal:
        _write_tick(journal, [_bundle(0)], payload={"turn": 1})
        _write_tick(journal, [_bundle(0)], payload={"turn": 2})
    reader = BundleJournal(path)
    logs = reader.replay()
    assert len(logs) == 2
    assert logs[0].payload_sha() != logs[1].payload_sha()
    assert reader.verify().ticks == 2


# -------------------------------------------------------------------- truncation


def test_truncated_final_line_is_reported_not_accepted(tmp_path):
    path = tmp_path / "journal.jsonl"
    with BundleJournal(path) as journal:
        _write_tick(journal, [_bundle(0)])
    good = path.read_bytes()
    path.write_bytes(good + b'{"kind":"tick_end"')

    reader = BundleJournal(path)
    records = list(reader.read())
    assert [record["kind"] for record in records][-1] == "tick_end"
    assert reader.last_read_report.truncated_tail is True
    assert reader.last_read_report.truncated_bytes > 0

    with pytest.raises(JournalTruncatedError, match="truncated"):
        reader.verify()
    # The complete prefix is still replayable when explicitly requested.
    assert reader.verify(allow_truncated=True).ticks == 1
    assert len(reader.replay(allow_truncated=True)) == 1


def test_malformed_middle_line_raises_with_line_number(tmp_path):
    records = _complete_records(tmp_path)
    path = tmp_path / "broken.jsonl"
    lines = [canonical_json(records[0]), "not json"]
    lines.extend(canonical_json(record) for record in records[1:])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(JournalCorruptionError, match="line 2"):
        list(BundleJournal(path).read())


# ------------------------------------------------------- coverage / duplication


@pytest.mark.parametrize("kind", ["result", "ack", "commit"])
def test_missing_bundle_record_is_rejected(tmp_path, kind):
    records = _complete_records(tmp_path)
    target = _bundle(0).bundle_id
    filtered = []
    for record in records:
        if record["kind"] == kind:
            payload = record.get(kind)
            bundle_id = (record.get("bundle_id") if kind == "commit"
                         else payload["bundle_id"])
            if bundle_id == target:
                continue
        filtered.append(record)
    path = _write_records(tmp_path / f"missing_{kind}.jsonl", filtered)
    with pytest.raises(JournalVerifyError, match=f"missing its {kind}"):
        BundleJournal(path).verify()


def test_missing_tick_end_is_rejected(tmp_path):
    records = _complete_records(tmp_path)
    path = _write_records(tmp_path / "no_end.jsonl", records[:-1])
    with pytest.raises(JournalVerifyError, match="open tick"):
        BundleJournal(path).verify()


@pytest.mark.parametrize("kind", ["dispatch", "result", "ack", "commit"])
def test_duplicate_record_is_rejected(tmp_path, kind):
    records = _complete_records(tmp_path)
    index = next(index for index, record in enumerate(records)
                 if record["kind"] == kind)
    duplicated = records[:index + 1] + [records[index]] + records[index + 1:]
    path = _write_records(tmp_path / f"duplicate_{kind}.jsonl", duplicated)
    with pytest.raises(JournalVerifyError, match=f"duplicate {kind}"):
        BundleJournal(path).verify()


def test_result_for_undispatched_bundle_is_rejected(tmp_path):
    records = _complete_records(tmp_path)
    index = next(index for index, record in enumerate(records)
                 if record["kind"] == "result")
    extra = json.loads(json.dumps(records[index]))
    extra["result"]["bundle_id"] = "not-dispatched"
    path = _write_records(tmp_path / "extra.jsonl",
                          records[:index] + [extra] + records[index:])
    with pytest.raises(JournalVerifyError, match="undispatched"):
        BundleJournal(path).verify()


def test_ack_without_result_is_not_a_complete_tick(tmp_path):
    records = _complete_records(tmp_path)
    target = _bundle(0).bundle_id
    filtered = [record for record in records
                if not (record["kind"] == "result"
                        and record["result"]["bundle_id"] == target)]
    path = _write_records(tmp_path / "ack_no_result.jsonl", filtered)
    with pytest.raises(JournalVerifyError, match="missing its result"):
        BundleJournal(path).verify()


# ------------------------------------------------------- checksums / revisions


def _tamper_result(records):
    for record in records:
        if record["kind"] == "result":
            record["result"]["output_sha"] = "0" * 64
            return records
    raise AssertionError("no result record")


def _tamper_execution(records):
    records[-1]["execution_sha"] = "0" * 64
    return records


def _tamper_revision(records):
    records[-1]["revision"] = BASE - 1
    return records


@pytest.mark.parametrize("tamper,match", [
    (_tamper_result, "output_sha"),
    (_tamper_execution, "execution_sha"),
    (_tamper_revision, "revision"),
])
def test_checksum_or_revision_mismatch_is_rejected(tmp_path, tamper, match):
    records = tamper(_complete_records(tmp_path))
    path = _write_records(tmp_path / "tampered.jsonl", records)
    with pytest.raises(JournalVerifyError, match=match):
        BundleJournal(path).verify()


def test_non_monotonic_commit_order_is_rejected(tmp_path):
    path = tmp_path / "non_monotonic.jsonl"
    with BundleJournal(path) as journal:
        _write_tick(journal, [_bundle(0), _bundle(1)],
                    committed_versions=[5, 4], revision=5)
    with pytest.raises(JournalVerifyError, match="not monotonic"):
        BundleJournal(path).verify()


# ------------------------------------------------------------- append semantics


def test_duplicate_append_is_rejected_without_a_second_line(tmp_path):
    path = tmp_path / "journal.jsonl"
    bundle = _bundle(0)
    with BundleJournal(path) as journal:
        journal.tick_start(RUN, BASE, base_version=BASE, revision=BASE)
        journal.dispatch(bundle)
        with pytest.raises(DuplicateRecordError):
            journal.dispatch(bundle)
        with pytest.raises(BundleJournalError):
            journal.tick_start(RUN, BASE, base_version=BASE, revision=BASE)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_duplicate_commit_append_is_rejected(tmp_path):
    path = tmp_path / "journal.jsonl"
    bundle = _bundle(0)
    result = _result(bundle)
    ack = _ack(bundle, result, BASE + 1)
    with BundleJournal(path) as journal:
        journal.tick_start(RUN, BASE, base_version=BASE, revision=BASE)
        journal.dispatch(bundle)
        journal.result(result)
        journal.ack(ack)
        journal.commit(bundle.bundle_id, BASE + 1)
        with pytest.raises(DuplicateRecordError):
            journal.commit(bundle.bundle_id, BASE + 1)
    assert list(BundleJournal(path).read())[-1]["kind"] == "commit"


def test_path_validation_and_lazy_creation(tmp_path):
    with pytest.raises(JournalPathError):
        BundleJournal(tmp_path)  # a directory, not a file
    with pytest.raises(JournalPathError):
        BundleJournal("")

    path = tmp_path / "not_yet" / "journal.jsonl"
    journal = BundleJournal(path)
    assert not path.exists(), "construction must not create the file"
    journal.close()
    assert not path.exists()

    blocker = tmp_path / "plain_file"
    blocker.write_text("not a directory", encoding="utf-8")
    under_file = BundleJournal(blocker / "journal.jsonl")
    with pytest.raises(JournalPathError, match="cannot open"):
        under_file.tick_start(RUN, BASE, base_version=BASE, revision=BASE)
    under_file.close()


# ------------------------------------------------------- partitioned integration


SMALL_SCENARIO = {
    "id": "dr02_bundle_room",
    "name": "DR02 bundle room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
        {"name": "Cy", "role": "farmer", "backend": "simple", "home_cell": [3, 3]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [],
    "laws": [],
    "policies": [],
    "charters": [],
}


class _FixedRestBackend(CheapBackend):
    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("rest", {"kind": "dr02_rest"}))


def _journal_game(tmp_path, executor):
    path = tmp_path / "logs" / "bundles.jsonl"
    game = create_game(
        scenario=SMALL_SCENARIO, seed=305000, default_backend="simple",
        autonomous=True, llm_log=False, executor=executor,
        affordance_mode="menu", snapshot_mode="on_demand",
        bundle_log_path=str(path))
    for actor in game.characters:
        game.set_backend(actor, _FixedRestBackend(game.characters[actor]))
    game.world._actor_positions["Ada"] = (1, 1)
    game.world._actor_positions["Ben"] = (100, 100)
    game.world._actor_positions["Cy"] = (200, 200)
    return game, path


def test_partitioned_game_journal_replays_to_last_bundle_log(tmp_path):
    game, path = _journal_game(tmp_path, "partitioned")
    for _ in range(2):
        assert game.step()["status"] == "advanced"

    assert path.is_file()
    journal = game.bundle_journal
    records = list(journal.read())
    assert records[0]["kind"] == "tick_start"
    assert records[-1]["kind"] == "tick_end"
    assert sum(record["kind"] == "tick_end" for record in records) == 2

    report = journal.verify()
    assert report.ticks == 2
    assert report.aborted_ticks == 0
    assert report.bundles >= 6

    logs = journal.replay()
    assert len(logs) == 2
    assert logs[-1].to_dict() == game.last_bundle_log.to_dict()
    for log in logs:
        assert log.committed_order == tuple(log.dispatched)
        assert set(log.acks) == set(log.dispatched)
    journal.close()


@pytest.mark.parametrize("executor", ["serial", "threaded"])
def test_non_partitioned_game_writes_no_journal(tmp_path, executor):
    game, path = _journal_game(tmp_path, executor)
    assert game.step()["status"] == "advanced"

    assert game.last_bundle_log is None
    assert game.bundle_journal is not None
    assert not path.exists(), f"{executor} must not create a journal file"
    assert list(game.bundle_journal.read()) == []
    game.bundle_journal.close()
