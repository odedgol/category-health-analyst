"""Tests for `resolve_site_with_learning`: LLM fallback only when needed, and it's cached.

Uses the real `DuckDbRepository` (via `temp_duckdb`) as the `SiteAliasStore`
— these tests care about real persistence round-tripping, not just
in-memory behavior. `fake_chat_model` (conftest.py) has no configured
response by default, so any test that doesn't explicitly configure one
fails loudly if the code unexpectedly reaches the LLM.
"""

import duckdb

from category_insights.agent.site_resolution import (
    LearnedSiteAliases,
    SiteClassification,
    resolve_site_with_learning,
)
from category_insights.db.repository import DuckDbRepository
from category_insights.sites import DEFAULT_SITE_ID
from tests.conftest import FakeChatModel


def test_known_site_name_resolves_without_any_llm_call(
    temp_duckdb: duckdb.DuckDBPyConnection, fake_chat_model: FakeChatModel
) -> None:
    learned_aliases = LearnedSiteAliases(DuckDbRepository(temp_duckdb))

    result = resolve_site_with_learning("Canada", fake_chat_model, learned_aliases)

    assert result == 2
    assert fake_chat_model.structured_call_counts == {}


def test_none_mention_resolves_to_default_without_any_llm_call(
    temp_duckdb: duckdb.DuckDBPyConnection, fake_chat_model: FakeChatModel
) -> None:
    learned_aliases = LearnedSiteAliases(DuckDbRepository(temp_duckdb))

    result = resolve_site_with_learning(None, fake_chat_model, learned_aliases)

    assert result == DEFAULT_SITE_ID
    assert fake_chat_model.structured_call_counts == {}


def test_unrecognized_mention_calls_the_llm_and_learns_it(
    temp_duckdb: duckdb.DuckDBPyConnection, fake_chat_model: FakeChatModel
) -> None:
    repository = DuckDbRepository(temp_duckdb)
    learned_aliases = LearnedSiteAliases(repository)
    fake_chat_model.set_structured_response(SiteClassification, SiteClassification(site_id=77))

    result = resolve_site_with_learning("Bavaria", fake_chat_model, learned_aliases)

    assert result == 77
    assert fake_chat_model.structured_call_counts[SiteClassification] == 1
    assert repository.list_learned_aliases() == {"bavaria": 77}


def test_the_same_mention_resolved_again_does_not_call_the_llm_a_second_time(
    temp_duckdb: duckdb.DuckDBPyConnection, fake_chat_model: FakeChatModel
) -> None:
    """The test that actually proves convergence toward zero LLM calls."""
    repository = DuckDbRepository(temp_duckdb)
    first_run_aliases = LearnedSiteAliases(repository)
    fake_chat_model.set_structured_response(SiteClassification, SiteClassification(site_id=77))
    resolve_site_with_learning("Bavaria", fake_chat_model, first_run_aliases)

    # Fresh LearnedSiteAliases, as a new process would build at startup —
    # loads from the same persisted store, not the in-memory object above.
    second_run_aliases = LearnedSiteAliases(repository)
    empty_chat_model = FakeChatModel()  # no response configured: any call raises

    result = resolve_site_with_learning("Bavaria", empty_chat_model, second_run_aliases)

    assert result == 77
    assert empty_chat_model.structured_call_counts == {}


def test_llm_returning_no_match_falls_back_without_caching(
    temp_duckdb: duckdb.DuckDBPyConnection, fake_chat_model: FakeChatModel
) -> None:
    repository = DuckDbRepository(temp_duckdb)
    learned_aliases = LearnedSiteAliases(repository)
    fake_chat_model.set_structured_response(SiteClassification, SiteClassification(site_id=None))

    result = resolve_site_with_learning("Narnia", fake_chat_model, learned_aliases)

    assert result == DEFAULT_SITE_ID
    assert repository.list_learned_aliases() == {}  # not cached: a real answer may exist later


def test_llm_returning_an_invalid_site_id_is_not_trusted_or_cached(
    temp_duckdb: duckdb.DuckDBPyConnection, fake_chat_model: FakeChatModel
) -> None:
    repository = DuckDbRepository(temp_duckdb)
    learned_aliases = LearnedSiteAliases(repository)
    fake_chat_model.set_structured_response(SiteClassification, SiteClassification(site_id=999))

    result = resolve_site_with_learning("Somewhere", fake_chat_model, learned_aliases)

    assert result == DEFAULT_SITE_ID
    assert repository.list_learned_aliases() == {}
