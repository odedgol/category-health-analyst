# Known Issues

Bugs and limitations, logged as they're found during development. Each
entry is marked resolved (with the sprint that fixed it) or left open.

## Resolved

- **Low-confidence category matches were offered as a confident "did you
  mean X?"** Found live-testing the Streamlit app with a real
  `OPENAI_API_KEY`: `"kicks"` landed on `"Women's Running Shoes"` as the
  semantic handler's top candidate, but at a low raw similarity score,
  and the graph still phrased it as "did you mean 'Board Games'?" — a
  *different*, wrong category, presented with unwarranted confidence.
  **Fixed** in `agent/graph.py`'s `resolve_category_node`: only a
  `"medium"`-confidence match gets a named "did you mean"; `"low"` (and
  no match at all) gets an honest "I don't recognize that category."
  See `docs/CHANGELOG.md` / `docs/DESIGN.md`.

- **The mock catalog had no men's shoes category.** Reported live: asking
  about `"Men's Running Shoes"` always resolved to `"Women's Running
  Shoes"` instead. Not a matching bug — the fixture genuinely had no
  men's-shoes category to find, only `"Women's Running Shoes"` and
  (unrelated) `"Men's Dress Shirts"`. **Fixed** by adding category 19,
  `"Men's Running Shoes"`, to `fixtures/categories.yaml`.

- **A clarifying question could never actually be answered.** The
  biggest one: `agent.graph`'s clarification flow ("Which category are
  you asking about?") had no memory of itself. Every chat message was
  extracted as a totally isolated question, so replying to the
  clarification — even with a real, exact category name — produced the
  *same* clarifying question again, forever. From the user's side this
  reads as the app being frozen/stuck, not as a conversation. **Fixed**:
  `intent_extraction.extract_intent()` gained a `history` parameter
  (recent turns, oldest first) that's included in the extraction prompt
  so a short reply is read in the context of what it's answering;
  `agent/graph.py`'s `AgentState`/`answer_question()` and `ui/app.py`
  now thread the actual chat history through on every turn.

- **A "why did X change" question with no period silently showed a
  snapshot instead of addressing "what changed."** Raised directly: the
  model should notice a real change in the data and ask which one the
  user means, not guess or stay quiet about it. **Fixed**: added
  `agent/change_detection.py` (`find_change_points`, a robust z-score
  over day-over-day deltas) and `agent/graph.py`'s `detect_change` node
  — a `wants_explanation` question with no period now looks at the real
  metric history and asks about a real, data-grounded change point
  instead. See `docs/CHANGELOG.md` / `docs/DESIGN.md` for the threshold
  calibration.

## Open

- **Category resolution can only be as good as the embedding model lets
  it be.** A mention with no literal text overlap and only a loose
  semantic relationship to the intended category (e.g. `"footwear"` for
  `"Women's Running Shoes"`) can still land below the confidence
  thresholds and get an honest-but-unhelpful "I don't recognize that
  category," even though a human would understand it immediately. The
  category-list sidebar (Sprint 6+) mitigates this by letting a user see
  the real catalog instead of guessing, but doesn't eliminate it.

- **Confirming a detected change point doesn't yet trigger an automatic
  before/after comparison.** Replying to "I see a notable change around
  DATE — which one?" with that date (e.g. `"2026-06-27"`) currently
  resolves to a single-day snapshot value, not a period comparison with
  notes attached — `wants_explanation` from the original turn isn't
  carried into the follow-up's fetch behavior. The right fix is likely
  turning a confirmed change-point date into an automatic "just before
  vs. at/after that date" comparison; not built yet.
