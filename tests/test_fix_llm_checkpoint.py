"""fix_llm_ops: an LLM resident can be checkpointed, and an LLM game writes its complete log by default.

The checkpoint tests call bigville/llm_checkpoint.py directly and always run. The game tests save and load a game
through bigville/game_persistence.py, which is untracked in this tree: each of them skips when that module is not
importable. Every game built here passes ``llm_log=False`` unless the test is about the log."""
from __future__ import annotations

import gzip
import json

import pytest

from bigville.api import create_game
from bigville.backends.autopilot import CallBudget
from bigville.backends.cheap import SimplePolicy
from bigville.backends.llm import LLMBackend
from bigville.llm_checkpoint import checkpoint_llm_backend, llm_budget_for, restore_llm_backend
from bigville.llm_log import LOG_DIR_ENV, read_log, verify_log
from bigville.llm_scenario import RunDigest, build_llm_town
from llm_stub import FakeProvider, varied_reply


def _town(provider, residents=2):
    return build_llm_town(provider, llm_residents=residents, llm_log=False)


def _json(data):
    return json.loads(json.dumps(data, sort_keys=True))


def _same(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _calls(records):
    return [r for r in records if r["kind"] == "call"]


# -- the checkpoint module, called directly ----------------------------------------------------

def test_an_llm_checkpoint_is_json_data_and_restores_the_same_state():
    provider = FakeProvider(varied_reply)
    game = _town(provider)
    for _ in range(3):
        game.step()
    name = game.llm_residents[0]
    backend = game.backends[name]
    data = _json(checkpoint_llm_backend(backend))
    assert data["kind"] == "llm"
    assert data["schema"] == "bigville/llm-checkpoint/1"
    assert data["resident"] == name
    restored = restore_llm_backend(data, game.characters[name], provider)
    assert _same(restored.to_dict(), backend.to_dict())
    assert restored.concurrency == backend.concurrency
    assert (restored.thread_chars, restored.full_every) == (backend.thread_chars, backend.full_every)
    assert restored.budget.max_calls_per_day == backend.budget.max_calls_per_day
    assert restored.budget.calls_by_day == backend.budget.calls_by_day
    assert restored.autopilot.policy == backend.autopilot.policy


def test_a_run_stopped_and_resumed_from_llm_checkpoints_matches_the_uninterrupted_run():
    turns, stop_at = 6, 3

    def run(stop: bool):
        provider = FakeProvider(varied_reply)
        game = _town(provider)
        names = list(game.llm_residents)
        digest = RunDigest()
        before_stop: dict[str, int] = {}
        for turn in range(turns):
            for name in names:                       # a consult every turn, so the threads grow across the stop
                game.backends[name].gate.last_consult_turn = None
            if stop and turn == stop_at:
                for call in provider.calls:
                    before_stop[call["meta"]["actor"]] = before_stop.get(call["meta"]["actor"], 0) + 1
                data = {name: _json(checkpoint_llm_backend(game.backends[name])) for name in names}
                shared = llm_budget_for(data.values())
                for name in names:
                    game.set_backend(name, restore_llm_backend(data[name], game.characters[name], provider,
                                                               budget=shared))
            assert game.step()["status"] == "advanced"
            digest.add(game)
        per_actor: dict[str, list] = {}
        for call in provider.calls:          # per resident (the global call order varies with the thread pool)
            per_actor.setdefault(call["meta"]["actor"], []).append(call["payload"]["messages"])
        return digest.hexdigest(), per_actor, names, before_stop

    control_digest, control_sent, names, _ = run(stop=False)
    resumed_digest, resumed_sent, _, before_stop = run(stop=True)
    assert resumed_digest == control_digest
    assert resumed_sent == control_sent
    # The first consult of each resident after the stop carries the thread it had before: its messages hold a reply.
    continued = [sent[before_stop[actor]] for actor, sent in resumed_sent.items()
                 if before_stop.get(actor) and len(sent) > before_stop[actor]]
    assert continued
    assert all(any(m["role"] == "assistant" for m in messages) for messages in continued)



def test_restoring_an_llm_resident_without_a_provider_says_why():
    game = _town(FakeProvider(varied_reply), residents=1)
    name = game.llm_residents[0]
    data = checkpoint_llm_backend(game.backends[name])
    with pytest.raises(ValueError, match="needs a provider"):
        restore_llm_backend(data, game.characters[name], None)


def test_a_checkpoint_is_refused_for_another_resident_or_an_unknown_kind_or_schema():
    provider = FakeProvider(varied_reply)
    game = _town(provider, residents=2)
    first, second = game.llm_residents
    data = checkpoint_llm_backend(game.backends[first])
    with pytest.raises(ValueError, match="checkpoint is for"):
        restore_llm_backend(data, game.characters[second], provider)
    with pytest.raises(ValueError, match="unsupported LLM checkpoint schema"):
        restore_llm_backend(dict(data, schema="bigville/llm-checkpoint/0"), game.characters[first], provider)
    with pytest.raises(ValueError, match="not an LLM checkpoint"):
        restore_llm_backend(dict(data, kind="cheap"), game.characters[first], provider)


def test_a_policy_with_a_callback_is_refused_at_checkpoint_and_not_silently_dropped():
    game = _town(FakeProvider(varied_reply), residents=1)
    character = game.characters[game.llm_residents[0]]
    backend = LLMBackend(character, FakeProvider(varied_reply), policy=SimplePolicy(hook=lambda *a, **k: None))
    with pytest.raises(TypeError, match="hook"):
        checkpoint_llm_backend(backend)


def test_the_autopilot_policy_survives_json_including_its_tuple_fields():
    game = _town(FakeProvider(varied_reply), residents=1)
    character = game.characters[game.llm_residents[0]]
    policy = SimplePolicy(allow_stock_fetches=True, stock_fetch_kinds=("grain", "bread"),
                          action_bonuses={"rest": 2.0})
    backend = LLMBackend(character, FakeProvider(varied_reply), policy=policy)
    restored = restore_llm_backend(_json(checkpoint_llm_backend(backend)), character, FakeProvider(varied_reply))
    assert restored.autopilot.policy == policy
    assert restored.autopilot.policy.stock_fetch_kinds == ("grain", "bread")


def test_residents_restored_with_one_shared_budget_keep_every_residents_day_counts():
    provider = FakeProvider(varied_reply)
    game = _town(provider, residents=2)
    for _ in range(4):
        game.step()
    names = list(game.llm_residents)
    data = {name: _json(checkpoint_llm_backend(game.backends[name])) for name in names}
    shared = llm_budget_for([{"kind": "cheap"}, *data.values()])     # non-LLM entries are ignored
    restored = {name: restore_llm_backend(data[name], game.characters[name], provider, budget=shared)
                for name in names}
    assert all(restored[name].budget is shared for name in names)
    assert shared.calls_by_day == game.backends[names[0]].budget.calls_by_day
    assert shared.spent == game.backends[names[0]].budget.spent
    assert llm_budget_for([{"kind": "cheap"}]) is None


def test_separate_budgets_are_merged_by_union_of_their_day_counts():
    provider = FakeProvider(varied_reply)
    game = _town(provider, residents=2)
    names = list(game.llm_residents)
    for name in names:                       # create_game gives each LLM resident its own budget
        game.backends[name].budget = CallBudget(max_calls_per_day=50)
    for _ in range(4):
        game.step()
    merged = llm_budget_for([_json(checkpoint_llm_backend(game.backends[n])) for n in names])
    expected = {}
    for name in names:
        expected.update(game.backends[name].budget.calls_by_day)
    assert merged.calls_by_day == expected
    assert merged.max_calls_per_day == 50


# -- the game: save, load and continue (needs the untracked bigville/game_persistence.py) ------

@pytest.mark.parametrize("residents", [0, 2])
def test_a_game_saved_and_loaded_continues_to_the_same_run_digest(tmp_path, residents):
    gp = pytest.importorskip("bigville.game_persistence")
    turns, stop_at = 6, 3

    def run(stop: bool):
        provider = FakeProvider(varied_reply)
        game = _town(provider, residents=residents)
        digest = RunDigest()
        for turn in range(turns):
            if stop and turn == stop_at:
                path = tmp_path / f"ck-{stop_at}-{residents}"
                gp.save_game_checkpoint(game, path)
                game = gp.load_game_checkpoint(path, llm_provider=provider, llm_log=False)
            assert game.step()["status"] == "advanced"
            digest.add(game)
        per_actor: dict[str, list] = {}
        for call in provider.calls:          # per resident (the global call order varies with the thread pool)
            per_actor.setdefault(call["meta"]["actor"], []).append(call["payload"]["messages"])
        return digest.hexdigest(), per_actor

    control = run(stop=False)
    resumed = run(stop=True)
    assert resumed[0] == control[0]
    assert resumed[1] == control[1]
    assert bool(control[1]) == (residents > 0)


def test_a_game_with_llm_residents_refuses_to_load_without_a_provider(tmp_path):
    gp = pytest.importorskip("bigville.game_persistence")
    game = _town(FakeProvider(varied_reply), residents=1)
    gp.save_game_checkpoint(game, tmp_path / "ck")
    with pytest.raises(ValueError, match="needs a provider"):
        gp.load_game_checkpoint(tmp_path / "ck", llm_log=False)


def test_a_loaded_game_writes_its_llm_log_to_the_chosen_directory(tmp_path):
    gp = pytest.importorskip("bigville.game_persistence")
    provider = FakeProvider(varied_reply)
    game = _town(provider, residents=2)
    game.step()
    gp.save_game_checkpoint(game, tmp_path / "ck")
    before = len(provider.calls)
    restored = gp.load_game_checkpoint(tmp_path / "ck", llm_provider=provider, llm_log_dir=str(tmp_path / "logs"))
    for _ in range(3):
        for name in game.llm_residents:           # the consult gate would not call the model here: force a consult
            restored.backends[name].gate.last_consult_turn = None
        restored.step()
    made = len(provider.calls) - before
    files = sorted((tmp_path / "logs").glob("*.jsonl.gz"))
    assert made > 0
    assert len(files) == 1 and restored.llm_log.path.resolve() == files[0].resolve()
    assert verify_log(files[0]).ok
    assert len(_calls(read_log(files[0]))) == made


# -- the default log (fix_llm_ops, the decision that an LLM run attaches the complete log) -----

def test_an_llm_game_writes_its_complete_log_to_the_default_directory_under_the_working_directory(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(LOG_DIR_ENV, raising=False)
    provider = FakeProvider(varied_reply)
    game = build_llm_town(provider, llm_residents=1)
    for _ in range(3):
        game.step()
    files = sorted((tmp_path / "runs" / "llm_logs").glob("*.jsonl.gz"))
    assert len(files) == 1
    assert game.llm_log.path.resolve() == files[0].resolve()
    assert verify_log(files[0]).ok
    assert len(_calls(read_log(files[0]))) == len(provider.calls) > 0
    assert gzip.open(files[0]).read(1) == b"{"


def test_the_environment_variable_chooses_the_log_directory_and_create_game_attaches_too(
        tmp_path, monkeypatch):
    monkeypatch.setenv(LOG_DIR_ENV, str(tmp_path / "env"))
    provider = FakeProvider(varied_reply)
    game = create_game(scenario="town100", default_backend="llm", llm_provider=provider)
    assert game.llm_log is not None
    assert game.llm_log.path.parent == tmp_path / "env"
    assert all(game.backends[n].log is game.llm_log for n in game.characters if n != game.player)
    game.llm_log.append({"kind": "probe"})
    assert read_log(game.llm_log.path) == [{"run_id": game.llm_log.run_id, "kind": "probe"}]


def test_a_game_without_llm_residents_or_with_the_log_off_creates_no_file_or_directory(tmp_path):
    game = create_game(scenario="town100", default_backend="cheap", llm_log_dir=str(tmp_path / "none"))
    assert game.llm_log is None
    assert not (tmp_path / "none").exists()
    provider = FakeProvider(varied_reply)
    off = build_llm_town(provider, llm_residents=1, llm_log=False, llm_log_dir=str(tmp_path / "off"))
    off.step()
    assert provider.calls and off.llm_log is None
    assert not (tmp_path / "off").exists()


def test_the_default_log_is_redacted_with_the_providers_redact_and_nothing_else_is_changed(tmp_path):
    secret = "KEY-123"
    reply = json.dumps({"major_action": None, "utterances": [{"text": secret}]})

    class RedactingProvider(FakeProvider):
        def redact(self, text):
            return str(text).replace(secret, "[redacted]")

    provider = RedactingProvider(reply)
    game = build_llm_town(provider, llm_residents=1, llm_log_dir=str(tmp_path))
    game.step()
    path = game.llm_log.path
    raw = gzip.open(path).read().decode("utf-8")
    assert secret not in raw
    assert "[redacted]" in raw
    assert verify_log(path).ok
