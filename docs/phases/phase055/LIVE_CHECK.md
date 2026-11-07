# Live check of the OpenCode Go provider (2026-11-06)

Run by the supervising session, with the key from `.env` (never printed; the response body and the log were checked
for it). Model `glm-5.3-flash`, base URL `https://opencode.ai/inference/go/openai/v1`. Three calls in total.

## What the response looks like

- `usage.opencode.allowance` is a **number**: the cost of that call (1.225e-05 for a 35-token prompt and a 14-token
  reply; 0.0001154 for a 66-token prompt and a 211-token reply). `usage.opencode` also carries `billing_source`
  ("go"), `list_cost`, and `tokens` (`input`, `output`, `reasoning`, cache read and write). `usage.cost` is 0.
  `allowance_cost` reads the number correctly, so `last_cost`, `CallBudget` and `BIGVILLE_LLM_BUDGET` work on it.
- The reasoning field is **`message.reasoning_content`**. It is present on every response (empty with no reasoning)
  and holds the thinking text (589 characters for a short arithmetic prompt). It is not in `usage` beyond a count:
  `usage.completion_tokens_details.reasoning_tokens` (0 and 201 in the two calls). Phase 066's log keeps it whole.
- `max_tokens` includes reasoning tokens, as the plan said.
- JSON mode (`response_format`) was accepted.
- Request identity: the only id-like response header is `CF-RAY` (picked up as `request_id`); `x-opencode-log-id`
  is also sent and is kept in the logged headers.
- Other top-level keys: `choices`, `created`, `id`, `model`, `object`, `usage`. Message keys: `annotations`,
  `content`, `reasoning_content`, `refusal`, `role`.

## A real resident through the whole stack

`build_llm_town(provider, llm_residents=1, settings=...)`, five turns, a consult forced on turn 0: one call, one
accepted reply (a carry-on, so the autopilot's walk ran), no fallback, cost 0.000551, 3548 prompt tokens, 38
output tokens, 14 reasoning tokens. The complete log verified (1 record, mode `full`, thinking stored, key absent).
The later turns held the walk and made no call, as Phase 059 intends.

This closes the Phase 055 open question about the allowance shape. It does not measure model quality.
