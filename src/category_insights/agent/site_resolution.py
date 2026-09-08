"""Site resolution with LLM fallback and learning — converges toward zero LLM calls.

`sites.match_known_site` (a plain, static lookup) handles every mention
that matches a known site name or built-in alias, with no LLM involved.
Only a mention that matches *neither* the static registry nor a
previously learned alias reaches the LLM — and once it does, the answer
is persisted (`SiteAliasStore`), so the exact same phrase never needs a
second LLM call. Deliberately a plain module, not a Chain of
Responsibility class — see `sites.py` for why sites don't need that
machinery.
"""

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from category_insights.domain.ports import ChatModel, SiteAliasStore
from category_insights.sites import DEFAULT_SITE_ID, SITES, SITES_BY_ID, match_known_site


class LearnedSiteAliases:
    """In-memory cache of DB-persisted learned aliases, loaded once at startup.

    Reads are served from memory (no DB round-trip per question);
    `learn()` updates the in-memory cache *and* writes through to the
    store, so the cache is correct for the rest of this process
    immediately, not just after a restart.
    """

    def __init__(self, alias_store: SiteAliasStore) -> None:
        self._alias_store = alias_store
        self._aliases: dict[str, int] = alias_store.list_learned_aliases()

    def get(self, normalized_mention: str) -> int | None:
        return self._aliases.get(normalized_mention)

    def learn(self, normalized_mention: str, site_id: int) -> None:
        self._aliases[normalized_mention] = site_id
        self._alias_store.save_learned_alias(normalized_mention, site_id)


class SiteClassification(BaseModel):
    """The LLM's answer to "which known site (if any) does this mention refer to?"."""

    site_id: int | None


def _build_classification_prompt(mention: str) -> str:
    site_list = "\n".join(f"- {site.site_id}: {site.name}" for site in SITES)
    return (
        "A user mentioned a site/region that doesn't exactly match any known "
        "name or alias. Classify it against this closed list of known sites — "
        "return the matching site_id, or null if none of them plausibly match "
        "(do not guess).\n\n"
        f"Known sites:\n{site_list}\n\n"
        f"Mention: {mention!r}"
    )


def resolve_site_with_learning(
    mention: str | None, chat_model: ChatModel, learned_aliases: LearnedSiteAliases
) -> int:
    """Resolve a site mention, falling back to an LLM classification that gets learned.

    1. No mention at all -> `DEFAULT_SITE_ID` (not a resolution failure).
    2. Matches the static registry (`sites.match_known_site`) -> return it, no LLM call.
    3. Matches a previously learned alias -> return it, no LLM call.
    4. Otherwise, ask the LLM to classify it against the known sites. A
       valid answer is learned (persisted) before being returned, so the
       same mention never reaches the LLM again. An uncertain answer
       (`None`, or a `site_id` the LLM invented that isn't actually in
       the registry — never trusted blindly) falls back to
       `DEFAULT_SITE_ID` *without* being cached, so a genuinely
       ambiguous mention gets a fresh chance next time rather than a
       wrong answer being locked in.
    """
    if mention is None:
        return DEFAULT_SITE_ID

    known = match_known_site(mention)
    if known is not None:
        return known

    normalized = mention.strip().lower()
    learned = learned_aliases.get(normalized)
    if learned is not None:
        return learned

    structured_model = chat_model.with_structured_output(SiteClassification)
    classification = structured_model.invoke(
        [HumanMessage(content=_build_classification_prompt(mention))]
    )

    if classification.site_id is not None and classification.site_id in SITES_BY_ID:
        learned_aliases.learn(normalized, classification.site_id)
        return classification.site_id

    return DEFAULT_SITE_ID
