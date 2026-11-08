# Phase 061 live run: the speech parser against glm-5.3-flash (OpenCode Go)

Date 2026-11-08. Script: `docs/phases/phase061/live_run.py`. Model `glm-5.3-flash` through `bigville/providers/opencode_go.py`
(key from `.env`, never printed or written). The 200 labelled utterances of `tests/fixtures/speech_labelled.json`,
run through `SpeechParser` with a cache, 6 workers. Items the grammar places (47) make no call.

| Arm | Placed | Correct | Misplaced | Precision | Recall | Calls | Cost |
|---|---|---|---|---|---|---|---|
| Grammar only | 47 | 85 | 7 | 0.851 | 0.258 | 0 | 0 |
| Scripted perfect model (fake provider, earlier) | 155 | 193 | 7 | 0.955 | 0.955 | 153 | n/a |
| Live, first prompt | 194 | 140 | 55 | 0.716 | 0.897 | 160 | 0.0203 |
| Live, null instruction added (run A) | 149 | 178 | 13 | 0.913 | 0.877 | 163 | 0.0227 |
| Live, same prompt (run B, in `live/`) | 150 | 170 | 17 | 0.887 | 0.858 | 163 | 0.0229 |

Findings:
- With the first prompt the model placed 44 of the 45 lines that carry no act (labels null) as `share`, `smalltalk` or
  `complaint`, although the pack's own example shows such a line as act null. That cost 55 misplacements.
- Adding an instruction that most lines are not acts, and to reply act null when in doubt, cut the misplacements to 13
  and 17 in two runs. That instruction is now in the `intro` of `SPEECH_PARSER.prefix` (both packs), so the
  fixed reference changed (2796 bytes, sha256 f9ec5e86e6d9).
- The two runs of the same prompt differ by 8 correct placements: the model is not deterministic. A cached answer is
  deterministic once stored, but an unplaced line is not cached, so a second pass re-asks about 12 lines.
- About 10 to 12 replies per run were rejected (`invented_name`: a name slot that is not the speaker, the listener or
  a name in view) and repaired once; 1 to 2 stayed unplaced as `invalid_output`.
- Remaining errors: questions read as requests or offers (`Can you help me with the fence?` as a question), and a few
  greetings, thanks and small talk the model calls null. Mean latency 1.6 s a call, 163 calls, about 0.023 in total.
- The model's thinking (`reasoning_content`) is in the provider result and is not kept by this script.
