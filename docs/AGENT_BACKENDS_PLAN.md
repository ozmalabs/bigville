# Pluggable agent backends and prompt protocol

This is the implementation plan for making Bigville support real LLM agents
alongside Ocelot and a deterministic game-style backend. The existing
`CognitionBackend` protocol, `ActorContext`, `ActorResponse`, capability
markers, and read-only held-state dump are the seam to preserve.

## 1. Freeze the backend contract

Every backend receives an immutable turn context and returns a structured
proposal. It never mutates the world directly.

The response schema should remain:

```json
{
  "major_action": {"action": "...", "params": {"...": "..."}},
  "utterances": [{
    "target": "person-id",
    "act": "inform",
    "slots": {"content": "..."},
    "content": "optional free text"
  }],
  "memory_updates": [],
  "waiting": false
}
```

The world is the admissibility authority. Invalid, unavailable, too-costly, or
already-consumed proposals are rejected as ordinary failed actions and are
returned to the backend as a result. No backend gets a hidden bypass.

Communication capabilities remain explicit per actor:

```json
{
  "mode": "free_text|templated",
  "supports_free_text": true,
  "requires_conversational_interface": false
}
```

## 2. Add a prompt builder, not prompt strings in the world

Create `bigville/backends/prompts.py` with a versioned `PromptBuilder` that
turns `ActorContext` into three parts:

1. **System contract** — the actor is a resident, may choose one major action,
   speech is free, and the world validates everything.
2. **Private character state** — identity, personality, memories, held frame
   seeds, goals, beliefs, and current backend state. Private state must never
   be mixed into public observations.
3. **Turn packet** — calendar, body state, position, inventory, observations,
   public laws/policies/documents, admissible affordances, and recipient
   communication capabilities.

The builder should support `format="json"` and a human-readable debug format,
and return a prompt record containing `schema_version`, `system`, `context`,
`requested_output_schema`, and a redacted audit view. Prompt construction must
be deterministic for a fixed context so it can be replayed in tests.

The LLM must be told that:

- it cannot invent possessions, facts, people, shop transactions, or world
  changes;
- affordances are the available choices for this turn, not suggestions to
  reinterpret;
- speech addresses people, not buildings or abstract shops;
- free-text speech must become a templated act/slot message when the recipient
  requires the conversational interface;
- asking, accepting, and replying are utterances/free actions, while a major
  physical/economic action is separate;
- one major action is permitted, but multiple free utterances may be emitted;
- silence and waiting are valid choices.

## 3. Implement `LLMBackend`

Add a transport-neutral backend with a small provider protocol:

```python
class LLMProvider(Protocol):
    def complete(self, request: PromptRequest) -> str | dict: ...
```

The backend should provide:

- provider injection for OpenAI-compatible, local, and test transports;
- model, temperature, timeout, retry, and token-budget configuration;
- structured-output mode where supported;
- JSON extraction and strict schema validation where it is not;
- one repair attempt containing only validation errors;
- a safe `waiting` response after repeated invalid output;
- prompt/response hashes and latency in backend state, never private secrets;
- no network dependency in the core package import path.

An LLM backend is `free_text` capable by default, but it must still inspect
`recipient_interfaces` and send structured acts to templated-only recipients.
The world adapter remains responsible for the final communication envelope.

## 4. Replace the current cheap policy with a deterministic game backend

Add a `DeterministicBackend` rather than hiding game logic in the world. It
should feel like conventional simulation AI while remaining reproducible:

- score only the published affordances;
- use needs (hunger, health, energy), explicit goals, work role, inventory,
  safety, travel cost, social commitments, and expected utility;
- reserve food and tools before selecting work;
- prefer reachable actions and account for path length and body energy;
- choose speech from structured social goals and recipient capabilities;
- use a seeded tie-breaker, stable actor id, and stable action ordering;
- return a reason trace with score components for debugging;
- never schedule a world action outside the actor tick and never mutate state.

This backend should have scenario profiles such as `villager`, `merchant`,
`farmer`, and `constable`, but those profiles should be data/configuration,
not Python branches that bypass admissibility.

## 5. Testing and evaluation gates

Add fixtures that replay the same context through every backend and compare:

- all returned actions are schema-valid and world-admissible;
- no actor gets an action without the required object, route, energy, or food;
- free-text and templated conversation interoperate in both directions;
- private memories and held frames never appear in another actor's prompt;
- deterministic decisions are byte-for-byte stable under a fixed seed;
- LLM retries cannot create duplicate actions or duplicate transactions;
- a failed action is observable to the next cognition tick;
- prompt versions can be replayed against recorded contexts.

Only after those tests pass should provider-specific integrations and model
selection be added.

## Suggested implementation order

1. `prompts.py` plus prompt snapshot tests.
2. `DeterministicBackend` plus replay/economy survival tests.
3. response validation and result feedback in `BigvilleGame`.
4. provider protocol and `LLMBackend` with a fake provider.
5. OpenAI-compatible and local providers as optional extras.
6. prompt/evaluation datasets from recorded Bigville turns.
