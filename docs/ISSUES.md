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

- **`detect_change` always asked "which date?," even with only one
  honest answer.** A single real change point still triggered a
  clarifying question, and a reply that didn't add a new date (e.g. just
  re-stating the category) bounced back into the identical question —
  the same "stuck" pattern as the history bug above, in a new spot.
  **Fixed**: a single, unambiguous candidate is now acted on directly —
  `detect_change_node` writes a before/after window straight into
  `intent` and the graph proceeds to `fetch_data`, explaining the change
  instead of asking about it. Only a genuine conflict between metrics
  still routes to `clarify`.

- **A wrong `category_mention` from earlier in the conversation could
  survive a correction.** Reported live: `"what cause the change in the
  Aligned taxonomy"` (not a real category) → correctly asked which
  category → `"Women's Running Shoes"` → the *same* "I don't recognize
  'Aligned taxonomy'" message came back, ignoring the correction.
  Root cause, verified live and reproduced consistently: `gpt-4o-mini`
  can keep an earlier, wrong extracted value instead of the one the
  latest message is correcting it with — this held even after
  strengthening the extraction prompt with an explicit
  "latest message overrides earlier ones" instruction; prompting alone
  didn't fix it. **Fixed** deterministically instead:
  `resolve_category_node` gained `_last_turn_asked_about_category()` —
  when resolution fails right after our own category clarification, it
  retries against the raw latest message directly, bypassing
  extraction's judgment for that one field.

## Open

- **Category resolution can only be as good as the embedding model lets
  it be.** A mention with no literal text overlap and only a loose
  semantic relationship to the intended category (e.g. `"footwear"` for
  `"Women's Running Shoes"`) can still land below the confidence
  thresholds and get an honest-but-unhelpful "I don't recognize that
  category," even though a human would understand it immediately. The
  category-list sidebar (Sprint 6+) mitigates this by letting a user see
  the real catalog instead of guessing, but doesn't eliminate it.

- **The stale-`category_mention` fallback is scoped to "right after our
  own category clarification."** It won't catch the same
  keep-the-earlier-value failure mode in other fields (a stale
  `metric_keys`/`date_phrase`/`site_mention` carried forward
  incorrectly) — only `category_mention`, and only immediately following
  one of the three specific clarification messages
  `resolve_category_node` itself generates. A broader fix would need a
  more general "the latest message corrects field X" mechanism, not
  built yet.
