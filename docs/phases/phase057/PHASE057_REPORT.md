# Phase 057: a terminal interface (TUI)

## Summary

`python -m bigville.tui --player NAME` plays one resident from the agent view (Phase 052) and nothing else.
It has three parts:

- **Render.** `bigville/tui/render.py` draws an 80 by 24 screen from a view: status bar, map, a character sheet
  in five tabs, a log, and a prompt. Every line is words.
- **Commands.** `bigville/tui/commands.py` turns a typed line into a reply in the shape the LLM backend sends.
  It validates with `reply_schema.check` and binds handles with `reply_schema.to_wire`. Unknown verbs go to the
  world. Only a line with no letters is refused locally.
- **Connection.** Embedded (`EmbeddedClient`, an in-process game) or HTTP (`HttpClient`, `/api/view` and
  `/api/turn`). Neither class fetches `/api/state` or has a referee option.

Phase 029 reactions appear as an interrupt. The view gained a `reaction` section (words only) for them.

Fog (Phase 053) is not built. The map is the 15 by 15 patch the view already gives, with `level: "full"`. The
renderer also draws `hidden` and `vague`, from data the view does not carry yet.

Two limits of the existing server stop the TUI from playing over HTTP (see Limits). Embedded play works
fully.

Status: both entity self-tests pass with 0 errors and 0 warnings. `tests/test_phase057_tui.py` has 44 tests, all
passing. The simple backend's 60-turn town100 run is identical to HEAD. The full suite result is in Validation.

## Changes

### Created

- `bigville/tui/__init__.py`: package doc.
- `bigville/tui/__main__.py`: entry point. Options: `--player` (required), `--url`, `--scenario`, `--seed`,
  `--pack` (words, with `--url`), `--plain`, `--snapshot` (print one screen and exit). No referee option.
- `bigville/tui/render.py`: `render(view, width, height, tab, log, bottom, bottom_title, prompt, pack)`, pure;
  `sheet_lines`. The map is drawn by its `level` key: `full` (cells), `vague` (rows plus `labels`), `hidden`
  (blank, with the words for unseen ground).
- `bigville/tui/narrate.py`: sentences from the view with the pack's NARRATION templates. Covers the status,
  body feelings, people (`looking calm and lively`), speech heard, moves seen, the last action and its refusal
  reason, reaction prompts, the menu, and the arrival summary.
- `bigville/tui/commands.py`: `parse(text, view, pack)` returns `propose`, `ask`, `select`, `ui`, `pass`,
  `empty` or `unparsed`. `parse_reaction(text, view)` maps a reaction answer to its choice name.
- `bigville/tui/client.py`: `EmbeddedClient` (`view`, `affordances`, `submit`, `react`) and `HttpClient` (`view`,
  `submit`; `react` raises `UnsupportedOverHttp`). `affordances` is used only in process, to bind handles.
- `bigville/tui/app.py`: `Session` (one resident's view, the open menu or question, the log), `run_plain`
  (line mode over any text stream), `run_curses` (key loop over a screen object), `choose_front_end`.
- `domains/narration_check.py`: self-test for NARRATION. Each key names exactly the fields its template
  fills. No digit appears outside a field. Tab names and help lines are non-empty.
- `packs/bigville/world/narration.json` and `packs/test_hamlet/world/narration.json` (identical; written in
  exporter form, checked with `tools/export_pack.py` into a scratch directory). Templates, sheet labels, tab
  names and help lines. The words are the pack's, not code's.
- `tests/test_phase057_tui.py`: 44 tests (listed in Validation).
- `docs/phases/phase057/`: this report, self-test outputs, full-suite log, behaviour JSON and log for HEAD and
  for HEAD plus these hunks, the 80 by 24 sample and the plain transcript.

### Changed: the agent view (Phase 052 files, all edits from this phase)

- `domains/agent_view.py`:
  - `_map`: `level` is now the key `"full"` (it was the phrase "a patch of ground around you"). The phrase moved to
    `caption`. `MAP_LEVELS` (hidden, vague, full) is defined.
  - New `_reaction(game, actor, pack, known)`. While the actor is the holder of a pending eligible take, it returns
    `{from, what, amount, late, options: [{choice, words}]}`. `from` is the attacker's name if the actor knows it,
    otherwise "someone". `build_agent_view` adds `reaction` when this is present.
- `domains/agent_view_check.py`: `SECTIONS` gains `reaction` and `option`. `VIEW_WORD_KEYS` gains `react_resist`,
  `react_brace`, `react_evade`, `react_yield` and `reaction_late`.
- `packs/bigville/world/agent_view.json` and `packs/test_hamlet/world/agent_view.json` (identical):
  - `AGENT_VIEW_WHITELIST`: `top` gains `reaction`. `map` gains `caption`. New sections `reaction` (`from`, `what`,
    `amount`, `late`, `options`) and `option` (`choice`, `words`).
  - `VIEW_WORDS` gains `react_resist` ("hold on and resist"), `react_brace` ("brace yourself and hold on"),
    `react_evade` ("step out of their reach"), `react_yield` ("let it go") and `reaction_late` ("you are slow to
    answer"). Each has no digit.

Effect on the LLM prompt (Phase 054): the packet measures the whole `map` dict, so a real resident's prompt now
shows `level: "full"` and `caption`. The words are the same. No LLM run was made to check the prompt.

### Shared-file hunks (additive; rebuild from HEAD by applying these)

1. `domains/bigville_entities.py`, `check_consistency`. Anchor (unchanged line before the hunk):
   `    check_agent_view(_WORLD_PACK.path, errors, warnings, info)`. The hunk adds two lines after it:
   `    from domains.narration_check import check_narration  # Phase 057: the terminal interface's sentence templates`
   and `    check_narration(_WORLD_PACK.path, errors, warnings, info)`.
2. `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`, the manifest. Anchor: the `PROMPT_REPLY` entry,
   the last one in `tables`. At HEAD it is the multi-line object `{ "name": "PROMPT_REPLY", "file":
   "world/prompt_packet.json" }`, followed by `  ]`. The hunk adds `,` after that object and then the entry
   `{"name": "NARRATION", "file": "world/narration.json"}`. In the live tree, the same entry is one line, and
   the hunk adds `,` to it and the NARRATION line. Other sessions' edits are in both files; I changed only these lines.

No other shared file changed. `bigville/game.py`, `bigville/server.py`, `bigville/backends/*` (including
`ocelot.py`), `worlds/bigville_world.py` and `bigville/backends/reply_schema.py` are untouched.

No existing test was edited, and no assertion changed.

## Validation

Run from `/home/matt/ozmadev/bigville` on the live tree (other sessions' uncommitted work present).

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`. The info lines include
  `AGENT VIEW (bigville): 19 sections whitelisted, 30 referee-only names; all agent view checks pass` and
  `NARRATION (bigville): 32 templates, 5 tab names and the help lines; all narration checks pass`. Output:
  `docs/phases/phase057/selftest_bigville.txt`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, `ERRORS (0)`, `WARNINGS (0)`. Output:
  `docs/phases/phase057/selftest_test_hamlet.txt`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase057_tui.py`: 44 passed. The tests:
  - the 80 by 24 render of a fixed view matches an inline snapshot; the render is pure and repeats exactly;
    each sheet tab is in words with its tab bracketed; the test pack renders with its own words;
  - the map by level: hidden, vague (with labels), full; a view with no map is hidden; a too-small screen raises;
  - a real resident renders at 80 by 24 and shows the menu after `look`;
  - the parser: smash with a held tool and `hard` (value from INTENSITY_WORDS); aliases (bash, batter, pry, push);
    every intensity word and a numeric intensity; ambiguity ("open the chest" asks, listing `chest_1` and
    `chest_2`); a named one of several is chosen; walking to a known move row binds by handle and `to_wire` gives
    its destination; walking to an unknown place passes `toward`; a work line matches its menu row; `say` to a
    known resident; `take a few bread from ...` reads amount and source; wait, stop, quit, look, sheet and help;
    an unknown verb becomes an attempt that the schema accepts; only a line with no letters is unparsed; a
    menu number selects; reaction answers by number, name or words;
  - a scripted plain session on an embedded town100 game through `StringIO`, five turns, world turn +5;
  - a plain session with no input ends without quitting;
  - a contest on the player: the reaction appears in the view and on screen, a word answer resolves it, and the
    answer is echoed; an HTTP reaction is refused with a message and the session goes on;
  - the client classes have no `state` or `referee` name in their public methods or source;
  - over HTTP to a real agent-mode server on 127.0.0.1 port 0: the client makes only `/api/view` and `/api/turn`
    requests (the server records them), and a direct `GET /api/state` from the test gets 403;
  - a stub server on 127.0.0.1 port 0 records only `/api/view` and `/api/turn` from the client;
  - the curses loop on a fake screen (keys h, Tab, `:` + `wait`, Enter, `?`, `q`); the front-end choice falls
    back to plain when asked or when stdout is not a terminal; `--snapshot` prints 24 lines; `--referee` is
    rejected by argparse;
  - leak test: a town100 resident over a short run (look, wait, say, work, wait, look, wait, and two screens) has
    no digit in any rendered line except a handle the world published or a menu number; no pack referee-only name
    appears as a word; the leak check flags `energy: 42` and `hunger 0.5`; no NARRATION template has a digit
    outside its fields.
- Related files, run before the last narration edits (the `answered` echo and the waiting message):
  `pytest -q -p no:cacheprovider tests/test_phase052_agent_view.py tests/test_phase054_llm_prompt.py
  tests/test_phase051_lexicon.py tests/test_phase013a_packs.py tests/test_phase029_contest.py
  tests/test_phase031_llm_backend.py tests/test_phase059_autopilot.py tests/test_bigville_backends.py
  tests/test_bigville_game_api.py tests/test_phase057_tui.py`: 432 passed, 1 skipped. After the last edits,
  `tests/test_phase057_tui.py tests/test_phase052_agent_view.py tests/test_phase054_llm_prompt.py`: 106 passed.
- Canonical pack bytes: `python3 tools/export_pack.py --pack bigville --out <scratch>` and the same for
  `test_hamlet`. `world/narration.json`, `world/agent_view.json` and `pack.json` are byte-identical to the
  export, for both packs.
- Starting state: `git status --short` showed other sessions' changes, for example to `bigville/backends/*`,
  `worlds/bigville_world.py`, `bigville/server.py`, `domains/bigville_entities.py` and `packs/*/pack.json`, and
  untracked Ocelot and phase 034/048 files. I left them alone. My edits to the two shared files are the hunks
  listed above.
- Simple-backend behaviour (brief item): `PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py
  --label head|mine --turns 60`, town100, seed 305000, default seeding, run in two trees:
  `head` is `git archive HEAD`; `mine` is that archive plus the hunks above (view files, narration files,
  TUI package, the two shared-file hunks). Results: `behaviour_head.json` and `behaviour_mine.json`. They are
  identical except for `elapsed_seconds` and `label` (action counts: eat 5, move 3333, none 1050, rest 1549,
  sleep 48, work 15; utterances 300; hunger mean at end 2.4309; no deaths). `mine` was re-run on the final
  narration and TUI files.
- Full suite, final tree: `timeout 1700 python3 -m pytest -q -p no:cacheprovider` (log:
  `docs/phases/phase057/full_suite.log`): `4 failed, 1571 passed, 2 skipped` in 812 s. The four failures are:
  - the three Ocelot tests (`test_bigville_ocelot_communication`, `test_mixed_ocelot_checkpoint_parity`,
    `test_mixed_ocelot_village`), which fail with `worlds.bigville_ocelot_adapter` not importable. The brief says
    they fail on HEAD already, and I did not re-check that here;
  - `tests/test_phase058_persona.py::test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns`.
    It passes on `git archive HEAD` plus this phase's hunks. It also fails on a copy of the live tree with this
    phase's hunks reverted, so the cause is other sessions' uncommitted work, not this phase.

An earlier full run on a tree one edit behind this one gave `1569 passed, 2 skipped, 5 failed`. Its extra
failures were the Phase 058 test above and `tests/test_phase050_resolution.py::test_smashing_a_wooden_chest_damages_it_each_attempt_until_it_breaks_and_then_it_is_refused`.
The Phase 050 test passed when run alone, as its whole file, and in the final run. It did not reproduce, so I
have not attributed it to any cause.

Sample render (`python3 -m bigville.tui --player "Alby Marsh" --snapshot`, file
`docs/phases/phase057/sample_render_80x24.txt`):

```
Bigville   at dawn, spring, clear skies                                         
..........==...  [Body] Skills Knows Carrying People                            
..........=....  Work: councillor                                               
..........=....  Life: an adult, grown                                          
.........==....  Health: in good health                                         
.........=.....  Energy: fresh                                                  
.........=.....  Hunger: not hungry                                             
._...... ==.===  Strength: of ordinary strength                                 
_=__.._@.====..  Stamina: you have good wind                                    
_===__=====....  Mood: content                                                  
.__====...==...  Traits: pleasant enough; touchy; quick to take offence; stea...
...____....=...  Others see: looks pleasant; looks touchy; looks sunny; looks...
...........=...                                                                 
...........==..                                                                 
............=..                                                                 
............=..                                                                 
  unknown ground   . open grass   = a path   @ you   _ a floor                  
Your move                                                                       
A stranger (labourer) is right beside you, looking charming and lively.         
Peony Hobb is right beside you, looking charming and even-tempered.             
A stranger (labourer) is a few steps off, looking calm and easygoing.           
A stranger (labourer) is a few steps off, looking charming and even-tempered.   
Others are further off.                                                         
>                                                                               
```

Sample plain transcript (`printf 'look\nwait\nsay Kester: good morning\nwait\nwork burn charcoal\nwait\nquit\n' |
python3 -m bigville.tui --player "Alby Marsh" --plain`; file `docs/phases/phase057/sample_plain_transcript.txt`;
the echoed `>` lines are the input):

```
at dawn, spring, clear skies
You feel fresh.
You are not hungry.
You are in good health.
You feel content.
Kester Furlong is right beside you, looking even-tempered and lively.
A stranger (labourer) is right beside you, looking calm and even-tempered.
A stranger (labourer) is right beside you, looking charming and lively.
Peony Hobb is right beside you, looking charming and even-tempered.
A stranger (labourer) is a few steps off, looking calm and easygoing.
A stranger (labourer) is a few steps off, looking charming and even-tempered.
Others are further off.
> look
at dawn, spring, clear skies
You feel fresh.
You are not hungry.
You are in good health.
You feel content.
Kester Furlong is right beside you, looking even-tempered and lively.
A stranger (labourer) is right beside you, looking calm and even-tempered.
A stranger (labourer) is right beside you, looking charming and lively.
Peony Hobb is right beside you, looking charming and even-tempered.
A stranger (labourer) is a few steps off, looking calm and easygoing.
A stranger (labourer) is a few steps off, looking charming and even-tempered.
Others are further off.
You can
1. Burn charcoal
2. Grind flour
3. Brew ale
4. Make gruel
5. Propagate yeast
> wait
Time passes.
> say Kester: good morning
You say to Kester Furlong: "good morning"
> wait
Time passes.
> work burn charcoal
Last action: work. It happened.
> wait
Time passes.
> quit
```

Reaction prompt (from the embedded test contest; the holder is the player, the taker is Kester Furlong):

```
Answer
Kester Furlong is trying to take coin from you: a few.
1. hold on and resist
2. brace yourself and hold on
3. step out of their reach
4. let it go
>
```

Answering `2` gives `You brace yourself and hold on.`, then `Time passes.`

## Limits

- **HTTP cannot play a move, a work row or a reaction yet.** `bigville/server.py` `turn` passes the body to
  `ActorResponse.from_dict` and never calls `reply_schema.to_wire`, so a `can` handle (for example `target:4`
  or `work:grind_flour`) reaches the world without its params. By reading the code, a move then has no destination
  and a work row has no recipe, so the world should refuse them. I did not run these over HTTP. No HTTP
  route delivers a reaction: `/api/turn` calls `submit_player_response`, the decision queue, and the reaction
  queue (`HumanBackend.submit_reaction`) is never filled. `HttpClient.react` raises `UnsupportedOverHttp`, and
  the session shows that message. Both need a server hunk, see Open questions. Speech needs no binding, so it should
  work over HTTP; I tested HTTP only for `wait` and `say` (both in the stub-server test).
- **Fog is not built.** The map is the 15 by 15 terrain patch within sight range, with `level: "full"`. The
  `hidden` and `vague` drawings are tested with synthetic views only. The view has no `labels` field for vague
  landmarks, so the vague path draws nothing in real play.
- **Status bar.** It shows time, season and weather. It has no day counter (the view carries none) and no place
  name (the view names no current place). Both are omitted rather than invented.
- **Outcomes narrated.** Only what the view carries: the last major action (done, or not, and the refusal's
  description), speech heard, moves seen, and the reaction prompt. Damage, progress and strain are not in the
  view (Phase 052 limit), so they are not narrated. After a reaction the screen says what you answered but not
  how the take ended, because the view does not carry the contest's outcome.
- **Held tools.** `with hammer` is sent as the kind `hammer`. A held item's kind is read back from its words with
  spaces turned into underscores (`wooden bowl` becomes `wooden_bowl`). If that is not the kind the world uses,
  the world refuses the attempt.
- **Walking.** `h j k l` and the arrows send `walk west` and the rest. The world refuses these as malformed until
  `move toward` (Phase 053) exists. Walks to a known place go through the `can` rows and work.
- **`stop`** ends the turn with no action, like `wait`. The TUI never sets a continuation, so there is no walk to
  cancel.
- **Speech.** Heard text is printed as the other resident wrote it. The leak test checks the run it uses, which has
  no digit in speech. A resident who says a number would show it.
- **Curses.** The key loop is tested on a fake screen only. It was not run in a real terminal, and I did not look
  at its drawing there. Plain mode is the verified front end.
- **Parser scope.** Verb sets are fixed (for example take, give, say, walk, eat, work, sleep, rest). Other verbs
  become attempts. A name is matched on its words against the view. A name that matches nothing is passed as
  typed, and the world refuses it if it does not exist.
- **Size.** The layout is drawn for 80 by 24. `render` raises below 40 by 12. The curses loop renders at least
  40 by 12 and clips to the terminal, so a small terminal shows a cut-off screen rather than an error.

## Open questions

1. Server hunk for HTTP: in agent mode, `/api/turn` could call
   `reply_schema.to_wire(payload, pack, affordances=game.world.actor_affordances(player))` before
   `ActorResponse.from_dict`, and route a reaction body (for example `{"reaction": "resist"}`) to
   `HumanBackend.submit_reaction` while `game._suspended` is set. Is that in scope for this phase or a
   follow-up? I did not edit `server.py`, since it is outside the write scope.
2. Should a contest's outcome for its holder go into the view (a `contest` section with word outcomes such as
   "you kept hold of it")? It needs whitelisting and a words table.
3. The LLM packet now carries `caption` and `level: "full"` for the map. Accept, or keep the packet's map as it was?
4. Fog (053): the `vague` labels need a whitelisted `labels` field before the vague drawing does anything in play.

## Deviations from the brief

- The status bar has no day count or place name (not in the view).
- `map.level` changed from a phrase to a key, with the phrase moved to `caption`. This changes a Phase 052 field.
  It is the one change to an existing view field.
- The reaction fields and the reaction words were added as the brief allowed (word-only, whitelisted, documented).
- `game.py` and `server.py` were not changed, so HTTP play has the two limits above.

## Supervisor follow-up: HTTP play (server hunk)

The executor left HTTP play incomplete because `bigville/server.py` was outside its write scope. The supervisor
closed both gaps in the same commit, in agent mode only:

- `GameService._bind_reply(reply)`: a body `{"reply": {...}}` is checked with `reply_schema.check` and bound to the
  player's own affordance rows with `reply_schema.to_wire`, so a client sends words and handles, never the world's
  params. A schema error is a 400 with the errors in words.
- `GameService.turn`: a body `{"reaction": "resist"}` is delivered to the human backend's reaction queue
  (`HumanBackend.submit_reaction`) while a contested take is pending (`game._suspended`); with none pending it is a
  400 ("no reaction is pending"). A body with neither key is the plain `ActorResponse` body as before.
- `HttpClient.send_reply` posts `{"reply": ...}`; `HttpClient.react` posts `{"reaction": ...}`. `EmbeddedClient.send_reply`
  binds in process. `Session._propose` calls `client.send_reply`.
- Tests added (4): a menu row over HTTP is bound and enacted; a walk to a known place sends the row's destination;
  a reaction over HTTP reaches the holder; a bad reply and an unexpected reaction are refused. The old test that
  expected the HTTP reaction to be refused became a test that a client error is shown and the session goes on.

Shared-file hunks for this follow-up: `bigville/server.py` (a new `_bind_reply` method before `turn`, and a branch in
`turn` replacing the `ActorResponse.from_dict(payload)` / `submit_player_response` / `step` lines).
