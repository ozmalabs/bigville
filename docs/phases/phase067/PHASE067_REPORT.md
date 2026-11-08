# Phase 067 report: the terminal interface in two modes

## Summary

`python -m bigville.tui --player NAME` now has two modes, chosen with `--mode`:

- **`--mode map`**: the Phase 057 screen with character art. Each map glyph of the agent view is a two-character tile,
  and each person and thing the resident perceives has a glyph in the People tab and the legend.
- **`--mode text`**: a text adventure. The room is written from the prompt packet (Phase 054) that an LLM resident is
  given for the same moment, so the player sees what the packet carries and nothing else. Typed lines go through the
  same Session, the same reply binder (`reply_schema.check` and `to_wire`) and the same world step as the map mode.
  A line the grammar cannot place is asked again. A look or a walk writes the room again.

With no `--mode`, the screen is the Phase 057 screen. The default snapshot and a plain-mode transcript are
byte-identical to HEAD 5de0e52 (checked against a plain `git archive HEAD`, see Validation). The 057 tests pass unchanged.

Also in this phase:
- `around.writing` (Phase 064) reaches the prompt packet and the narrator, with reading on. With reading off, the packet
  body is identical to HEAD (see Validation). `pack_hash` in the packet record changes, because it hashes the whole pack.
- `--show-packet` prints the packet a text-mode room came from. `--log-dir` writes a hash-chained turn log (the
  Phase 066 `LLMLog`, without thinking, since a human has none).
- `TUI_ART` and `TUI_PROSE` are pack tables with a self-test. The self-test is at 0 errors and 0 warnings.
- A leak test covers both modes for raw numbers and referee-only names. The text mode's packet sections, and the
  view's top-level keys, are also checked against the agent view whitelist.

Four things the brief asked for are not built, and Limits says so: buildings as art, colour drawn on screen, free text
sent to the speech parser, and people placed on the map. The reasons are in Limits.

## Changes

### Created

- `bigville/tui/prose.py`: `room_lines(record, view, pack)` writes the room from a packet. `packet_text(record)` is the
  packet as printed (indented JSON).
- `bigville/tui/art.py`: `tiled(view, pack)` draws each map row as two-character tiles. `mark_people(view, pack, lines)`
  puts a person glyph in front of each People-tab line. `legend_items(view, pack)` lists the glyphs in use.
- `domains/tui_check.py`: self-test `check_tui(pack, errors, warnings, info)`. It checks every map glyph has a tile, tiles
  are two characters, colours come from the table's list, each prose template names exactly its declared fields, and no
  prose template or help line has a digit outside a field.
- `packs/bigville/world/tui_modes.json` and `packs/test_hamlet/world/tui_modes.json` (identical; exporter-canonical).
  Tables `TUI_ART` (tiles, people and thing glyphs, colours) and `TUI_PROSE` (text-mode sentences and help).
  Every value is presentation (APPROX, a model choice); none is a world fact.
- `tests/test_phase067_tui_modes.py`: 20 tests (listed in Validation).
- `docs/phases/phase067/build_clean_tree.py`: builds a clean tree from `git archive HEAD` plus this phase's files.
- `docs/phases/phase067/PHASE067_REPORT.md` (this file) and `docs/phases/phase067/logs/` (self-test, focused and full-suite
  logs); `docs/phases/phase067/sample_*.txt` (one text transcript, two 80 by 24 screens); `baseline_selftest_bigville.txt`
  and `run_057_after_first_edit.log` and `focused_working_tree.log` (run on the shared tree).

### Changed: terminal modules (`bigville/tui/`, all HEAD-clean before this phase)

- `bigville/tui/__main__.py`: `--mode {map,text}`, `--show-packet`, `--log-dir DIR`. Without `--mode`, the path is the
  HEAD path. `--mode text --url` and the two packet flags without `--mode text` exit with an argparse error.
- `bigville/tui/app.py`: `Session(client, pack, art=False, text=False)`. `screen()` passes `art` to render. `_line` asks
  again for an unplaced line in text mode. In text mode, `look` and `map` write the room, `help` gives the text help,
  and a walk sets `refresh`. `_propose` keeps the last reply for the log. New `run_text(session, inp, out, show_packet,
  log, echo)`.
- `bigville/tui/client.py`: `EmbeddedClient.packet()` builds the packet with `PromptBuilder` (the LLM path's builder), from
  `game._context(player)` with the agent view attached. `HttpClient.packet()` raises `UnsupportedOverHttp`.
- `bigville/tui/commands.py`: `placed(text, pack)`. True when the grammar knows the line's verb (a command word, a
  number, a wait, a lexicon verb). Used only in text mode.
- `bigville/tui/render.py`: `render(..., art=False)`. With `art`, the map is tiled, the People tab has glyphs, and the
  legend has glyph words. The default output is unchanged.
- `bigville/tui/narrate.py`: `around_lines` adds a sentence for each `around.writing` row (absent unless reading is on).

### Shared-file hunks (anchored; each anchor occurs once in HEAD 5de0e52)

1. `packs/bigville/pack.json`, manifest `tables`: after the last entry, `"name": "RECOGNISED_SEED", "file":
   "world/literacy.json"` followed by `}` and `]`. Two entries are added after it: `TUI_ART` and `TUI_PROSE`, both
   `"file": "world/tui_modes.json"`. The working tree's last entry is now 065's `IMPAIRMENT_NEIGHBOURS`, so in the
   working tree the two lines follow that entry instead. Same order of tables, different position in the list.
2. `packs/test_hamlet/pack.json`: the same hunk at the same anchor.
3. `packs/bigville/world/prompt_packet.json`, `caps`: after `"things": 800,`, add `"writing": 600,`.
4. `packs/test_hamlet/world/prompt_packet.json`: the same.
5. `bigville/backends/prompt_packet.py`, `build_packet`: before `    if consult_reason is not None:` (the line after the
   `public` dict), four lines: a comment, then `if around.get("writing"): public["around"]["writing"] =
   caps.items("writing", around["writing"])`.
6. `domains/prompt_packet_check.py`, `SECTIONS`: `"writing"` is added after `"things"` (the cap is required).
7. `domains/bigville_entities.py`, `check_consistency`: after `    check_narration(_WORLD_PACK.path, errors, warnings, info)`,
   two lines: `from domains.tui_check import check_tui` (with a Phase 067 comment) and `check_tui(_WORLD_PACK.path, errors,
   warnings, info)`. Phase 065 edits this file too; my two lines are additive and do not touch its hunks.

Phase 065 files: I did not edit `domains/agent_view.py`, `bigville/game.py`, `bigville/reporting.py`, `domains/impairment.py`
or `domains/impairment_check.py`. The only 065-owned files I touched are the two `pack.json` manifests and
`bigville_entities.py`, through the additive hunks above.

No existing test was edited, and no assertion changed. No `worlds/` file was touched.

## Validation

Shared tree: `/home/matt/ozmadev/bigville`, with other sessions' uncommitted work. Clean tree: `/tmp/t067_clean`, built by
`python3 docs/phases/phase067/build_clean_tree.py --out /tmp/t067_clean` from HEAD 5de0e52 plus this phase's files.

Starting state (`git status --short`, recorded before my first edit): modified `README.md`, `bigville/backends/ocelot.py`,
`bigville/game.py`, `bigville/game/game.js`, `bigville/reporting.py`, `bigville/seeds/bigville_actor_decision.json`,
`bigville/server.py`, `docs/AGENT_BACKENDS_PLAN.md`, `domains/agent_view.py`, `domains/bigville_entities.py`,
`packs/bigville/pack.json`, `packs/test_hamlet/pack.json`, three `tests/test_bigville_*` files, `worlds/bigville_world.py`;
untracked `.opencode/`, the Ocelot and mixed-village files, `docs/phases/phase065/`, `domains/impairment*.py`, the
`packs/*/world/impairment.json` files, and `docs/phases/phase052/full_suite_live_tree_midedit.log`. None of these were
mine, and I left them alone.

Commands and results:

- `python3 domains/bigville_entities.py` (working tree, final): exit 0, `ERRORS (0)`, `WARNINGS (0)`. Info:
  `TERMINAL MODES: 9 map tiles, 15 text sentences and 3 help lines; all terminal mode checks pass`.
  Log: `logs/selftest_bigville_working_tree.txt`.
- `python3 domains/bigville_entities.py` (clean tree): exit 0, `ERRORS (0)`, `WARNINGS (0)`. Log:
  `logs/selftest_bigville_clean_tree.txt`.
- `python3 -m domains.check --pack test_hamlet` (clean tree): exit 0, `ERRORS (0)`, `WARNINGS (0)`. Log:
  `logs/selftest_test_hamlet_clean_tree.txt`.
- `python3 tools/export_pack.py --pack bigville --out <scratch>`: `tui_modes.json`, `prompt_packet.json` and `narration.json`
  are byte-identical to the working tree's copies. `tui_modes.json` in `test_hamlet` is identical to `bigville`.
- Focused, clean tree: `pytest -q -p no:cacheprovider tests/test_phase052_agent_view.py tests/test_phase054_llm_prompt.py
  tests/test_phase054_actionable.py tests/test_phase062_perceiver.py tests/test_phase062b_perceiver_marks.py
  tests/test_phase064_reading.py tests/test_phase066_session_log.py tests/test_phase057_tui.py
  tests/test_phase067_tui_modes.py`: **221 passed** in 265 s, including the four 057 HTTP tests.
  Log: `logs/focused_clean_tree.log`.
- Focused, working tree (same command): **217 passed, 4 failed** in 267 s. The four failures are the 057 HTTP tests
  (`test_over_http_a_menu_row_is_bound...`, `test_over_http_walking_to...`, `test_over_http_a_reaction...`,
  `test_the_server_refuses_a_bad_reply...`). They fail on the shared tree because another session's uncommitted
  `bigville/server.py` changes the server. They pass on the clean tree, and they failed before my edits too (the first
  baseline run before my first edit showed the same four failures; its output was not saved to a file). Log:
  `focused_working_tree.log`.
- New tests `tests/test_phase067_tui_modes.py`: 20 passed (on the working tree, and again on the clean tree).
- `tests/test_phase057_tui.py` unchanged: 44 passed on the working tree, with the same four HTTP failures noted above.
- Full suite on the clean tree: `timeout 5400 python3 -m pytest -q -p no:cacheprovider -rfE` run from `/tmp/t067_clean`,
  log `logs/full_suite_clean_tree.log`. Result: **2226 passed, 5 skipped, 1 failed** in 4063 s (1:07:43). The failure is
  `tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`,
  a timing ratio under load (13.57 s concurrent against 15.97 s sequential, required below 0.75). Run alone on the same
  clean tree it passes: 6 passed (`logs/rerun_055_concurrency_clean_tree.log`). No management browser test failed.

Behaviour checks (run by hand; not claims about balance or performance):

- Default screen and plain transcript, against HEAD: `git archive HEAD` extracted to `/tmp/t067_head`, and the clean tree.
  `python3 -m bigville.tui --player "Alby Marsh" --snapshot` (no `--mode`) gives identical bytes in both trees. The same
  holds for `--plain` with input `look`, `wait`, `quit`. The default screen is in `sample_default_80x24.txt`.
- LLM packet, reading off, against HEAD: for three residents (Alby Marsh, Kester Furlong, Peony Hobb) the packet record
  from `PromptBuilder` in HEAD and in the clean tree differs only in `pack_hash` (`a17be1a4...` against `44a12d73...`
  for Alby Marsh). The packet body and system text are identical. `pack_hash` is the sha256 of the whole pack, so any
  pack edit changes it, including the two manifest entries and the new `caps.writing` (see Limits).
- Text mode, piped (`sample_text_mode.txt`): arrival, `look` (room written again), `wait`, `say Kester Furlong: good
  morning` (a say line), `wait`, `hello there` (asked again, the world not moved), `quit`.
- Map mode 80 by 24: `sample_map_mode_80x24.txt`. The legend line fits: `. open grass  = a path  @ you  T a tree  _ a floor
  & known  o stranger`.
- The turn log: one run of `look`, `wait`, `quit` wrote a log that `bigville.llm_log.verify_log` reports as ok.

## Limits

- **Map art is terrain, tiles and labels only.** The view draws the map from terrain alone, by design (`MAP_GLYPHS`: no
  occupants, no coordinates), and no view field gives a person's or a thing's cell. So a person or thing is a glyph in
  the People tab and the legend, not a symbol on the map. Placing them on the map needs a view change (a cell or bearing
  field, whitelisted and perceiver-tiered), which is outside this phase.
- **Fog levels are drawn as before.** The art tiles the `full` map. The `vague` and `hidden` levels (Phase 053) go through
  the 057 drawing, unchanged. The `vague` labels path is not exercised in play (057 limit), so the art does not change it.
- **No building art.** The view has no building cells. `TUI_ART` has no building entry, because one would draw nothing.
- **Colour is recorded, not drawn.** `TUI_ART` gives a colour per tile and per glyph. The plain text screen cannot draw
  colour, and the curses loop was not extended. The curses loop is not run in a real terminal here (as in 057).
- **Text mode is in-process only.** `--url` is refused. The packet is built from the game's resident context, which the
  server does not publish. A server route for the packet would be a server change, outside this phase.
- **Free text goes nowhere but "ask again".** The speech parser (Phase 061) places what a listener hears, from a speaker
  who gives no structure. A player's free text has no listener and no decided act. I did not wire the parser to player
  input. Text mode refuses a line whose verb the lexicon does not know, and it shows the words of `TUI_PROSE.unplaced`.
- **Lexicon verbs only.** Verbs the lexicon lacks (`unlock`, `light`, `fight`, `build`) are asked again in text mode,
  although the world may accept some of them through the map mode's attempt path. Adding verbs is a lexicon change.
- **No compass.** The view names no directions, so `go north` is not a command here. The exits are the view's own
  words (`walk toward the market`), and the typed form is `go toward the market`, or the number of the option.
- **Packet caps shape the room.** The packet caps the people list (`caps.people`), so a dense place shows fewer people.
  Text mode then says `Others are further off.`, as the map arrival does. The LLM resident sees the same list.
- **The packet has no contest section.** A reaction prompt in text mode comes from the view (`reaction`), not from the
  packet. The LLM path offers a reaction through `consult.choices`. Both show the same options.
- **Writing needs scripted marks.** The town declares no written marks (064). The tests script one sign. The packet and the
  room carry `writing` only when reading and perception are on.
- **The log is not the Phase 066 log.** Each record is `kind: text_turn` with the typed line, the packet as the resident had
  it (and its sha256), the reply in the LLM shape and the lines shown. There is no provider call, so no request messages,
  retries or thinking to record.
- **`pack_hash` changes for every LLM prompt record.** `PromptRecord.pack_hash` hashes the whole pack's base data, so
  this phase's pack edits (two manifest entries and the `writing` cap, in both packs) change it. The packet body does not
  change with reading off. A Phase 066 replay keyed on a prompt hash recorded before this phase will not match a prompt
  made after it, even though the content is the same. Any earlier pack edit did the same (Phases 062, 064, 065).
- **Five-turn script.** The brief's five turns are five lines on StringIO. Four of them advance the world (`wait`, `say`,
  `go`, `wait`); `look` does not.
- **Sizes.** The map art needs 30 columns for the map. The 80 by 24 screen still fits, but the sheet has about 48 columns.

## Open questions

1. Should a resident's cell or bearing enter the view (perceiver-tiered), so the map mode can place people and things?
2. Should text mode send free text to the speech parser, and to whom: the nearest resident, or a named one only?
3. Should the lexicon gain the verbs the world already runs (`unlock`, `light`, `fight`), or should text mode keep asking
   again for them?
4. Should a server route serve the packet, so text mode can play over HTTP?
5. Should the TUI draw colour through curses, once a real terminal check is possible?

## Deviations from the brief

- The brief says `--mode map` is the default. The instructions for this phase say that with no `--mode` the TUI behaves
  exactly as at HEAD. I followed the instructions: no `--mode` is the HEAD screen, and the art needs `--mode map`.
- Map art does not place people or things on the map (Limits).
- Buildings, colour and the speech-parser hookup are not built (Limits).
- The packet cap for `writing` is new (`caps.writing`, 600 characters), and `writing` is added to `SECTIONS`.
