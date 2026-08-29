import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings

from .models import AITaskRun, AITaskRunDocument, Document, DocumentChunk, DocumentShare, Entity, EntityMention, Notification, Relationship
from .services import ai_tasks_engine_service as ai_tasks_engine
from .services import dynamic_topk_service as dynamic_topk
from .services import graph_extraction_service as extraction
from .services import graph_retrieval_service as graph_retrieval
from .services import hyde_service as hyde
from .services import llm_client
from .services import query_expansion_service as expansion
from . import tasks
from .services import citation_service
from .services import context_compression_service as compression
from .services import health_service
from .services import llm_service
from .services import prompt_templates
from .services import query_service
from .services import query_transform_service as transform
from .services import reranker_service as reranker
from .services import retrieval_service as retrieval
from .services.graph_extraction_service import (
    ExtractedEntity,
    ExtractedRelationship,
    GraphExtractionResult,
)
from .services.graph_service import build_graph_for_chunk
from .services.multi_query_service import _reciprocal_rank_fusion, multi_query_search
from .services.retrieval_filters import RetrievalFilters, apply_document_filters


class EntityNormalizationTests(unittest.TestCase):
    """
    Pure normalization helpers - no DB, no LLM calls.
    """

    def test_normalize_entity_name_collapses_whitespace(self):
        self.assertEqual(
            extraction.normalize_entity_name("  Acme   Corp\n"),
            "Acme Corp",
        )

    def test_normalize_entity_key_is_case_insensitive(self):
        self.assertEqual(extraction.normalize_entity_key("Acme Corp"), "acme corp")
        self.assertEqual(extraction.normalize_entity_key("ACME CORP"), "acme corp")

    def test_normalize_entity_type_defaults_to_misc(self):
        self.assertEqual(extraction.normalize_entity_type(""), "MISC")
        self.assertEqual(extraction.normalize_entity_type(None), "MISC")

    def test_normalize_entity_type_uppercases_and_underscores(self):
        self.assertEqual(extraction.normalize_entity_type("job title"), "JOB_TITLE")

    def test_normalize_relation_type_defaults_to_related_to(self):
        self.assertEqual(extraction.normalize_relation_type(""), "RELATED_TO")

    def test_normalize_relation_type_uppercases_and_underscores(self):
        self.assertEqual(extraction.normalize_relation_type("works for"), "WORKS_FOR")


class GraphExtractionParsingTests(unittest.TestCase):
    """
    _parse_response() / extract_graph() - no live Gemini calls, the
    model is mocked so these run offline and deterministically.
    """

    def test_parse_response_valid_json(self):
        raw = (
            '{"entities": [{"name": "Ada Lovelace", "type": "person"}, '
            '{"name": "Analytical Engine", "type": "product"}], '
            '"relationships": [{"source": "Ada Lovelace", "relation": "designed for", '
            '"target": "Analytical Engine"}]}'
        )

        result = extraction._parse_response(raw)

        self.assertEqual(len(result.entities), 2)
        self.assertEqual(result.entities[0].name, "Ada Lovelace")
        self.assertEqual(result.entities[0].type, "PERSON")

        self.assertEqual(len(result.relationships), 1)
        self.assertEqual(result.relationships[0].relation, "DESIGNED_FOR")

    def test_parse_response_drops_relationships_with_unknown_entities(self):
        raw = (
            '{"entities": [{"name": "Ada Lovelace", "type": "person"}], '
            '"relationships": [{"source": "Ada Lovelace", "relation": "knows", '
            '"target": "Someone Never Extracted"}]}'
        )

        result = extraction._parse_response(raw)

        self.assertEqual(len(result.entities), 1)
        self.assertEqual(result.relationships, [])

    def test_parse_response_malformed_json_returns_empty_result(self):
        result = extraction._parse_response("not json at all")

        self.assertEqual(result.entities, [])
        self.assertEqual(result.relationships, [])

    def test_extract_graph_skips_short_text_without_calling_llm(self):
        with patch.object(extraction, "get_llm") as mock_get_llm:
            result = extraction.extract_graph("too short")

        mock_get_llm.assert_not_called()
        self.assertEqual(result.entities, [])

    def test_extract_graph_returns_empty_result_on_llm_failure(self):
        with patch.object(extraction, "get_llm", side_effect=RuntimeError("boom")):
            result = extraction.extract_graph(
                "Ada Lovelace worked with Charles Babbage on the Analytical Engine."
            )

        self.assertEqual(result.entities, [])
        self.assertEqual(result.relationships, [])

    def test_extract_graph_parses_mocked_llm_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (
            '{"entities": [{"name": "Charles Babbage", "type": "person"}], '
            '"relationships": []}'
        )

        with patch.object(extraction, "get_llm", return_value=mock_llm):
            result = extraction.extract_graph(
                "Charles Babbage designed the Difference Engine."
            )

        self.assertEqual(len(result.entities), 1)
        self.assertEqual(result.entities[0].name, "Charles Babbage")


class GraphConstructionTests(TestCase):
    """
    build_graph_for_chunk() against a real (test) database, with the
    LLM extraction call mocked so no network/API key is required.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw")

        self.document = Document.objects.create(
            user=self.user,
            title="Test Document",
            file="documents/test.txt",
        )

        self.chunk = DocumentChunk.objects.create(
            document=self.document,
            content="Ada Lovelace worked with Charles Babbage.",
            chunk_number=0,
        )

    def _extraction_result(self):
        return GraphExtractionResult(
            entities=[
                ExtractedEntity(name="Ada Lovelace", type="PERSON"),
                ExtractedEntity(name="Charles Babbage", type="PERSON"),
            ],
            relationships=[
                ExtractedRelationship(
                    source="Ada Lovelace",
                    relation="WORKED_WITH",
                    target="Charles Babbage",
                ),
            ],
        )

    def test_build_graph_creates_entities_and_relationship(self):
        with patch(
            "RAG.services.graph_service.extract_graph",
            return_value=self._extraction_result(),
        ):
            build_graph_for_chunk(self.chunk, self.user)

        self.assertEqual(Entity.objects.filter(user=self.user).count(), 2)
        self.assertEqual(Relationship.objects.filter(user=self.user).count(), 1)
        self.assertEqual(EntityMention.objects.filter(entity__user=self.user).count(), 2)

        relationship = Relationship.objects.get(user=self.user)
        self.assertEqual(relationship.weight, 1)
        self.assertEqual(relationship.relation_type, "WORKED_WITH")

    def test_build_graph_is_idempotent_and_increments_weight(self):
        with patch(
            "RAG.services.graph_service.extract_graph",
            return_value=self._extraction_result(),
        ):
            build_graph_for_chunk(self.chunk, self.user)
            build_graph_for_chunk(self.chunk, self.user)

        # Same chunk processed twice: no duplicate entities/mentions,
        # but the relationship weight reflects the repeat extraction.
        self.assertEqual(Entity.objects.filter(user=self.user).count(), 2)
        self.assertEqual(EntityMention.objects.filter(entity__user=self.user).count(), 2)

        relationship = Relationship.objects.get(user=self.user)
        self.assertEqual(relationship.weight, 2)

    def test_build_graph_skips_self_loop_relationships(self):
        result = GraphExtractionResult(
            entities=[ExtractedEntity(name="Ada Lovelace", type="PERSON")],
            relationships=[
                ExtractedRelationship(
                    source="Ada Lovelace",
                    relation="KNOWS",
                    target="Ada Lovelace",
                ),
            ],
        )

        with patch("RAG.services.graph_service.extract_graph", return_value=result):
            build_graph_for_chunk(self.chunk, self.user)

        self.assertEqual(Relationship.objects.filter(user=self.user).count(), 0)

    def test_build_graph_noop_on_extraction_failure(self):
        with patch(
            "RAG.services.graph_service.extract_graph",
            side_effect=RuntimeError("boom"),
        ):
            build_graph_for_chunk(self.chunk, self.user)

        self.assertEqual(Entity.objects.filter(user=self.user).count(), 0)


class GraphRetrievalTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pw")
        self.other_user = User.objects.create_user(username="other", password="pw")

        self.document = Document.objects.create(
            user=self.user,
            title="Test Document",
            file="documents/test.txt",
        )

        self.chunk = DocumentChunk.objects.create(
            document=self.document,
            content="Ada Lovelace pioneered early computing concepts.",
            chunk_number=0,
        )

        self.entity = Entity.objects.create(
            user=self.user,
            name="ada lovelace",
            display_name="Ada Lovelace",
            entity_type="PERSON",
            mention_count=1,
        )

        EntityMention.objects.create(entity=self.entity, chunk=self.chunk)

    def test_graph_search_returns_empty_without_user(self):
        self.assertEqual(graph_retrieval.graph_search("Who is Ada Lovelace?", None, 3), [])

    def test_graph_search_matches_entity_mentioned_in_question(self):
        results = graph_retrieval.graph_search("Who is Ada Lovelace?", self.user, 3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["document"], "Test Document")
        self.assertEqual(results[0]["search_type"], "graph")

    def test_graph_search_is_scoped_to_user(self):
        results = graph_retrieval.graph_search("Who is Ada Lovelace?", self.other_user, 3)

        self.assertEqual(results, [])

    def test_graph_search_no_match_returns_empty(self):
        results = graph_retrieval.graph_search("What's the weather today?", self.user, 3)

        self.assertEqual(results, [])


class DescribeSearchMethodTests(unittest.TestCase):
    """
    Pure function - no DB required.
    """

    def test_no_results_keeps_original_default_label(self):
        self.assertEqual(query_service.describe_search_method([]), "Hybrid (Vector + BM25)")

    def test_vector_and_bm25_only_matches_original_label(self):
        chunks = [{"search_type": "vector"}, {"search_type": "bm25"}]
        self.assertEqual(query_service.describe_search_method(chunks), "Hybrid (Vector + BM25)")

    def test_graph_contribution_is_reflected_in_label(self):
        chunks = [{"search_type": "vector"}, {"search_type": "graph"}]
        self.assertEqual(
            query_service.describe_search_method(chunks),
            "Hybrid (Vector + Graph)",
        )

    def test_hyde_and_multi_query_labels(self):
        chunks = [{"search_type": "hyde"}, {"search_type": "multi_query"}]
        self.assertEqual(
            query_service.describe_search_method(chunks),
            "Hybrid (HyDE + Multi-query)",
        )


class CalculateConfidenceTests(unittest.TestCase):
    """
    Pure function - no DB required.
    """

    def test_hyde_scores_count_toward_confidence_like_vector(self):
        # A close HyDE match (small L2 distance) should read as high
        # confidence, the same as an equally close vector match.
        vector_confidence = query_service.calculate_confidence(
            [{"search_type": "vector", "score": 0.1}]
        )
        hyde_confidence = query_service.calculate_confidence(
            [{"search_type": "hyde", "score": 0.1}]
        )
        self.assertEqual(vector_confidence, hyde_confidence)

    def test_bm25_and_multi_query_only_fall_back_to_neutral(self):
        chunks = [
            {"search_type": "bm25", "score": 5.0},
            {"search_type": "multi_query", "score": 0.05},
        ]
        self.assertEqual(query_service.calculate_confidence(chunks), 40)

    def test_not_found_answer_forces_zero_confidence(self):
        chunks = [{"search_type": "vector", "score": 0.01}]
        confidence = query_service.calculate_confidence(
            chunks, answer=prompt_templates.NOT_FOUND_ANSWER
        )
        self.assertEqual(confidence, 0)

    def test_zero_citations_discounts_confidence(self):
        chunks = [{"search_type": "vector", "score": 0.1}]

        uncited = query_service.calculate_confidence(
            chunks, answer="An answer with no markers.", citation_count=0
        )
        cited = query_service.calculate_confidence(
            chunks, answer="An answer [1].", citation_count=1
        )

        self.assertLess(uncited, cited)

    def test_citation_count_none_skips_discount(self):
        # Backward compatibility: omitting citation_count entirely
        # (existing callers) must not trigger the discount.
        chunks = [{"search_type": "vector", "score": 0.1}]
        self.assertEqual(
            query_service.calculate_confidence(chunks),
            query_service.calculate_confidence(chunks, citation_count=None),
        )

    def test_distance_past_one_still_yields_meaningful_confidence(self):
        # Regression: a flat `min(distance, 1.0)` cap used to clamp any
        # distance >= 1.0 straight to 0% confidence, even though 1.0 is
        # not "unrelated" for a normalized-embedding L2 distance (the
        # real range is 0..2). A distance of 1.0098 - the exact value
        # observed for a correct, cited answer in manual testing - must
        # read as a real, non-zero score, not 0%.
        chunks = [{"search_type": "vector", "score": 1.0098}]
        self.assertEqual(query_service.calculate_confidence(chunks), 49)

    def test_zero_distance_yields_near_maximum_confidence(self):
        # An exact embedding match (distance 0) should read as ~100%,
        # clamped to the function's 99 ceiling.
        chunks = [{"search_type": "vector", "score": 0.0}]
        self.assertEqual(query_service.calculate_confidence(chunks), 99)

    def test_orthogonal_distance_yields_zero_confidence(self):
        # For unit-length embeddings, a distance of sqrt(2) corresponds
        # to a cosine similarity of exactly 0 (orthogonal / unrelated).
        chunks = [{"search_type": "vector", "score": 2 ** 0.5}]
        self.assertEqual(query_service.calculate_confidence(chunks), 0)

    def test_maximum_distance_clamps_to_zero_not_negative(self):
        # Distance 2.0 (exact opposite vectors) maps to cosine
        # similarity -1, which must clamp to 0%, not go negative.
        chunks = [{"search_type": "vector", "score": 2.0}]
        self.assertEqual(query_service.calculate_confidence(chunks), 0)


class QueryTransformServiceTests(unittest.TestCase):
    """
    generate_query_variants() / _parse_variants() - no live Gemini
    calls, offline and deterministic.
    """

    def test_parse_variants_includes_original_first_and_dedupes(self):
        raw = (
            '{"variants": ["What is the capital of France?", '
            '"what is the capital of france?", "Name the capital of France"]}'
        )

        variants = transform._parse_response(raw, "What is the capital of France?")

        self.assertEqual(variants[0], "What is the capital of France?")
        # Second entry is a case-only duplicate of the question and
        # must be dropped; only the genuinely new phrasing survives.
        self.assertEqual(variants, [
            "What is the capital of France?",
            "Name the capital of France",
        ])

    def test_parse_variants_malformed_json_falls_back_to_question(self):
        self.assertEqual(transform._parse_response("nope", "Q"), ["Q"])

    def test_generate_query_variants_skips_short_question(self):
        with patch.object(transform, "get_llm") as mock_get_llm:
            result = transform.generate_query_variants("hi")

        mock_get_llm.assert_not_called()
        self.assertEqual(result, ["hi"])

    def test_generate_query_variants_falls_back_on_llm_failure(self):
        with patch.object(transform, "get_llm", side_effect=RuntimeError("boom")):
            result = transform.generate_query_variants("What is the capital of France?")

        self.assertEqual(result, ["What is the capital of France?"])


class QueryExpansionServiceTests(unittest.TestCase):
    """
    expand_query() - no live Gemini calls (generate_query_variants is
    mocked directly).
    """

    def test_expand_query_adds_new_terms_from_variants(self):
        with patch.object(
            expansion,
            "generate_query_variants",
            return_value=["Who is the CEO?", "Who leads the company as chief executive?"],
        ):
            expanded = expansion.expand_query("Who is the CEO?")

        self.assertTrue(expanded.startswith("Who is the CEO?"))
        for term in ("leads", "company", "chief", "executive"):
            self.assertIn(term, expanded)

    def test_expand_query_returns_original_when_no_new_terms(self):
        with patch.object(
            expansion, "generate_query_variants", return_value=["Who is the CEO?"]
        ):
            self.assertEqual(expansion.expand_query("Who is the CEO?"), "Who is the CEO?")

    def test_expand_query_falls_back_on_failure(self):
        with patch.object(
            expansion, "generate_query_variants", side_effect=RuntimeError("boom")
        ):
            self.assertEqual(expansion.expand_query("Who is the CEO?"), "Who is the CEO?")

    def test_expand_query_empty_question(self):
        self.assertEqual(expansion.expand_query(""), "")


class HydeServiceTests(unittest.TestCase):
    """
    generate_hypothetical_document() - no live Gemini calls.
    """

    def test_generates_passage_from_mocked_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Paris is the capital of France."

        with patch.object(hyde, "get_llm", return_value=mock_llm):
            passage = hyde.generate_hypothetical_document("What is the capital of France?")

        self.assertEqual(passage, "Paris is the capital of France.")

    def test_skips_short_question(self):
        with patch.object(hyde, "get_llm") as mock_get_llm:
            result = hyde.generate_hypothetical_document("hi")

        mock_get_llm.assert_not_called()
        self.assertEqual(result, "")

    def test_returns_empty_string_on_failure(self):
        with patch.object(hyde, "get_llm", side_effect=RuntimeError("boom")):
            result = hyde.generate_hypothetical_document("What is the capital of France?")

        self.assertEqual(result, "")

    def test_truncates_overly_long_passage(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "x" * 5000

        with patch.object(hyde, "get_llm", return_value=mock_llm):
            passage = hyde.generate_hypothetical_document("What is the capital of France?")

        self.assertEqual(len(passage), hyde.MAX_HYPOTHETICAL_CHARS)


class DynamicTopKServiceTests(unittest.TestCase):
    """
    compute_dynamic_top_k() - pure heuristic, no DB/LLM.
    """

    def test_short_question_keeps_base_top_k(self):
        self.assertEqual(
            dynamic_topk.compute_dynamic_top_k("Who is the CEO?", base_top_k=3), 3
        )

    def test_long_question_increases_top_k(self):
        question = "What are the main findings of the Q3 report and how do they compare"
        self.assertGreater(
            dynamic_topk.compute_dynamic_top_k(question, base_top_k=3), 3
        )

    def test_multi_part_question_gets_extra_bump(self):
        single = dynamic_topk.compute_dynamic_top_k(
            "What is our revenue this quarter and its breakdown by region", base_top_k=3
        )
        multi_part = dynamic_topk.compute_dynamic_top_k(
            "What is our revenue this quarter and also what is next quarter's forecast?",
            base_top_k=3,
        )
        self.assertGreaterEqual(multi_part, single)

    def test_result_is_capped_at_max(self):
        from django.conf import settings as dj_settings

        question = "word " * 100 + "and also or plus as well as"
        result = dynamic_topk.compute_dynamic_top_k(question, base_top_k=8)
        self.assertLessEqual(result, dj_settings.DYNAMIC_TOP_K_MAX)

    def test_empty_question_returns_base(self):
        self.assertEqual(dynamic_topk.compute_dynamic_top_k("", base_top_k=4), 4)


class ReciprocalRankFusionTests(unittest.TestCase):
    """
    _reciprocal_rank_fusion() - pure ranking math, no DB/LLM.
    """

    def test_item_found_in_multiple_lists_ranks_first(self):
        list_a = [
            {"content": "a", "document": "Doc1", "chunk_number": 0, "score": 0.1, "search_type": "vector"},
            {"content": "b", "document": "Doc2", "chunk_number": 1, "score": 0.2, "search_type": "vector"},
        ]
        list_b = [
            {"content": "b", "document": "Doc2", "chunk_number": 1, "score": 5.0, "search_type": "bm25"},
            {"content": "c", "document": "Doc3", "chunk_number": 0, "score": 4.0, "search_type": "bm25"},
        ]

        fused = _reciprocal_rank_fusion([list_a, list_b], top_k=3)

        self.assertEqual((fused[0]["document"], fused[0]["chunk_number"]), ("Doc2", 1))
        self.assertTrue(all(item["search_type"] == "multi_query" for item in fused))

    def test_respects_top_k_cap(self):
        list_a = [
            {"content": str(i), "document": "Doc", "chunk_number": i, "score": 0.0, "search_type": "vector"}
            for i in range(5)
        ]
        fused = _reciprocal_rank_fusion([list_a], top_k=2)
        self.assertEqual(len(fused), 2)

    def test_empty_lists_produce_empty_result(self):
        self.assertEqual(_reciprocal_rank_fusion([], top_k=3), [])
        self.assertEqual(_reciprocal_rank_fusion([[], []], top_k=3), [])


class MultiQuerySearchTests(unittest.TestCase):
    """
    multi_query_search() orchestration - variant generation and the
    underlying vector_search()/bm25_search() calls are all mocked.
    """

    def test_returns_empty_when_no_extra_variants(self):
        with patch(
            "RAG.services.multi_query_service.generate_query_variants",
            return_value=["only the original"],
        ):
            self.assertEqual(multi_query_search("only the original"), [])

    def test_returns_empty_on_variant_generation_failure(self):
        with patch(
            "RAG.services.multi_query_service.generate_query_variants",
            side_effect=RuntimeError("boom"),
        ):
            self.assertEqual(multi_query_search("question"), [])

    def test_fuses_results_from_extra_variants(self):
        variant_result = [
            {"content": "x", "document": "Doc1", "chunk_number": 0, "score": 0.1, "search_type": "vector"}
        ]

        with patch(
            "RAG.services.multi_query_service.generate_query_variants",
            return_value=["question", "a variant"],
        ), patch(
            "RAG.services.multi_query_service.vector_search", return_value=variant_result
        ), patch(
            "RAG.services.multi_query_service.bm25_search", return_value=[]
        ):
            results = multi_query_search("question", top_k=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["search_type"], "multi_query")

    def test_one_failing_variant_does_not_abort_the_others(self):
        good_result = [
            {"content": "x", "document": "Doc1", "chunk_number": 0, "score": 0.1, "search_type": "vector"}
        ]

        call_count = {"n": 0}

        def flaky_vector_search(variant, top_k=None, filters=None, user=None, accessible_document_ids=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("transient failure")
            return good_result

        with patch(
            "RAG.services.multi_query_service.generate_query_variants",
            return_value=["question", "variant one", "variant two"],
        ), patch(
            "RAG.services.multi_query_service.vector_search", side_effect=flaky_vector_search
        ), patch(
            "RAG.services.multi_query_service.bm25_search", return_value=[]
        ):
            results = multi_query_search("question", top_k=3)

        self.assertEqual(len(results), 1)


class RetrievalFiltersTests(unittest.TestCase):
    """
    RetrievalFilters / apply_document_filters() - query construction
    only (never evaluated against the DB), so these run without a
    live database connection.
    """

    def test_from_request_parses_valid_document_id(self):
        filters = RetrievalFilters.from_request(document_ids=["5"])
        self.assertEqual(filters.document_ids, (5,))
        self.assertFalse(filters.is_empty())

    def test_from_request_parses_multiple_document_ids(self):
        filters = RetrievalFilters.from_request(document_ids=["5", "6"])
        self.assertEqual(filters.document_ids, (5, 6))
        self.assertFalse(filters.is_empty())

    def test_from_request_ignores_invalid_document_id(self):
        filters = RetrievalFilters.from_request(document_ids=["not-an-int"])
        self.assertIsNone(filters.document_ids)
        self.assertTrue(filters.is_empty())

    def test_from_request_blank_document_ids_is_no_filter(self):
        filters = RetrievalFilters.from_request(document_ids=[])
        self.assertTrue(filters.is_empty())

    def test_apply_document_filters_is_noop_for_none(self):
        queryset = DocumentChunk.objects.all()
        self.assertIs(apply_document_filters(queryset, None, document_field="document"), queryset)

    def test_apply_document_filters_is_noop_for_empty_filters(self):
        queryset = DocumentChunk.objects.all()
        empty_filters = RetrievalFilters()
        result = apply_document_filters(queryset, empty_filters, document_field="document")
        self.assertEqual(str(result.query), str(queryset.query))

    def test_apply_document_filters_builds_expected_lookup(self):
        filters = RetrievalFilters(document_ids=(5, 6))
        queryset = apply_document_filters(
            DocumentChunk.objects.all(), filters, document_field="document"
        )
        self.assertIn("document_id", str(queryset.query))
        self.assertIn("IN (5, 6)", str(queryset.query))

    def test_apply_document_filters_combines_file_type_and_date(self):
        filters = RetrievalFilters(
            file_types=("pdf",), uploaded_after=date(2026, 1, 1)
        )
        queryset = apply_document_filters(
            DocumentChunk.objects.all(), filters, document_field="document"
        )
        sql = str(queryset.query)
        self.assertIn("file_type", sql)
        self.assertIn("uploaded_at", sql)


class RerankerServiceTests(unittest.TestCase):
    """
    rerank_chunks() - the cross-encoder model itself is mocked, so
    these run offline and deterministically.
    """

    def setUp(self):
        self.chunks = [
            {"content": "irrelevant", "document": "D1", "chunk_number": 0, "score": 0.1, "search_type": "vector"},
            {"content": "very relevant", "document": "D1", "chunk_number": 1, "score": 0.5, "search_type": "bm25"},
            {"content": "somewhat relevant", "document": "D2", "chunk_number": 0, "score": 0.3, "search_type": "vector"},
        ]

    def test_reorders_by_descending_cross_encoder_score(self):
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.1, 0.9, 0.5]

        with patch.object(reranker, "_get_reranker_model", return_value=mock_model):
            results = reranker.rerank_chunks("q", self.chunks)

        self.assertEqual(
            [r["content"] for r in results],
            ["very relevant", "somewhat relevant", "irrelevant"],
        )
        self.assertEqual(results[0]["rerank_score"], 0.9)

    def test_respects_top_k(self):
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.1, 0.9, 0.5]

        with patch.object(reranker, "_get_reranker_model", return_value=mock_model):
            results = reranker.rerank_chunks("q", self.chunks, top_k=2)

        self.assertEqual(len(results), 2)

    def test_preserves_existing_keys(self):
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.1, 0.9, 0.5]

        with patch.object(reranker, "_get_reranker_model", return_value=mock_model):
            results = reranker.rerank_chunks("q", self.chunks)

        self.assertEqual(results[0]["search_type"], "bm25")
        self.assertEqual(results[0]["document"], "D1")

    def test_does_not_mutate_input_chunks(self):
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.1, 0.9, 0.5]

        with patch.object(reranker, "_get_reranker_model", return_value=mock_model):
            reranker.rerank_chunks("q", self.chunks)

        self.assertNotIn("rerank_score", self.chunks[0])

    def test_empty_input_passthrough(self):
        self.assertEqual(reranker.rerank_chunks("q", []), [])

    def test_falls_back_to_original_order_on_failure(self):
        with patch.object(
            reranker, "_get_reranker_model", side_effect=RuntimeError("model load failed")
        ):
            results = reranker.rerank_chunks("q", self.chunks)

        self.assertEqual(results, self.chunks)

    def test_falls_back_respects_top_k(self):
        with patch.object(reranker, "_get_reranker_model", side_effect=RuntimeError("boom")):
            results = reranker.rerank_chunks("q", self.chunks, top_k=1)

        self.assertEqual(results, self.chunks[:1])


class ContextCompressionServiceTests(unittest.TestCase):
    """
    compress_context() - generate_embedding() is mocked with plain
    vectors chosen so cosine similarity is easy to reason about, so
    these run offline and deterministically.
    """

    def setUp(self):
        self.chunks = [
            {"content": "the sky is blue", "document": "D1", "chunk_number": 0, "score": 0.1, "search_type": "vector"},
            {"content": "the sky is blue today", "document": "D1", "chunk_number": 1, "score": 0.2, "search_type": "bm25"},
            {"content": "the ocean is deep", "document": "D2", "chunk_number": 0, "score": 0.3, "search_type": "vector"},
        ]

    def test_drops_near_duplicate_keeps_first_occurrence(self):
        # Chunks 0 and 1 are identical in embedding space (redundant);
        # chunk 2 is orthogonal (distinct).
        embeddings = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]

        with patch.object(compression, "generate_embedding", side_effect=embeddings):
            results = compression.compress_context(self.chunks)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["content"], "the sky is blue")
        self.assertEqual(results[1]["content"], "the ocean is deep")

    def test_keeps_all_distinct_chunks(self):
        embeddings = [[1.0, 0.0], [0.0, 1.0], [0.0, -1.0]]

        with patch.object(compression, "generate_embedding", side_effect=embeddings):
            results = compression.compress_context(self.chunks)

        self.assertEqual(len(results), 3)

    def test_single_chunk_returned_unchanged_without_embedding_call(self):
        with patch.object(compression, "generate_embedding") as m_embed:
            results = compression.compress_context(self.chunks[:1])

        self.assertEqual(results, self.chunks[:1])
        self.assertFalse(m_embed.called)

    def test_empty_list_returned_unchanged(self):
        self.assertEqual(compression.compress_context([]), [])

    def test_custom_threshold_overrides_settings(self):
        # Similarity 0.8 is below the default 0.92 threshold but above
        # a deliberately low custom threshold.
        embeddings = [[1.0, 0.0], [0.8, 0.6], [0.0, 1.0]]

        with patch.object(compression, "generate_embedding", side_effect=embeddings):
            results = compression.compress_context(self.chunks, similarity_threshold=0.5)

        self.assertEqual(len(results), 2)

    def test_falls_back_to_original_on_embedding_failure(self):
        with patch.object(compression, "generate_embedding", side_effect=RuntimeError("boom")):
            results = compression.compress_context(self.chunks)

        self.assertEqual(results, self.chunks)


class PromptTemplatesTests(unittest.TestCase):

    def test_is_not_found_answer_matches_fixed_fallback(self):
        self.assertTrue(
            prompt_templates.is_not_found_answer(prompt_templates.NOT_FOUND_ANSWER)
        )

    def test_is_not_found_answer_tolerant_of_whitespace_variation(self):
        self.assertTrue(
            prompt_templates.is_not_found_answer(
                "  I couldn't find the answer in the uploaded document.\n"
            )
        )

    def test_is_not_found_answer_false_for_real_answer(self):
        self.assertFalse(
            prompt_templates.is_not_found_answer("The launch date is March 2024 [1].")
        )

    def test_is_not_found_answer_false_for_empty_or_none(self):
        self.assertFalse(prompt_templates.is_not_found_answer(""))
        self.assertFalse(prompt_templates.is_not_found_answer(None))

    def test_build_answer_prompt_embeds_context_question_and_fallback(self):
        prompt = prompt_templates.build_answer_prompt(
            "[1] (Doc, chunk 0):\nSome content", "What is it?"
        )

        self.assertIn("[1] (Doc, chunk 0):\nSome content", prompt)
        self.assertIn("What is it?", prompt)
        self.assertIn(prompt_templates.NOT_FOUND_ANSWER, prompt)


class CitationServiceTests(unittest.TestCase):

    def setUp(self):
        self.chunks = [
            {"content": "Revenue grew 20%.", "document": "Q3 Report", "chunk_number": 0, "score": 0.1, "search_type": "vector"},
            {"content": "Costs fell 5%.", "document": "Q3 Report", "chunk_number": 1, "score": 0.2, "search_type": "bm25"},
        ]

    def test_build_cited_context_numbers_chunks_in_order(self):
        context = citation_service.build_cited_context(self.chunks)

        self.assertIn("[1] (Q3 Report, chunk 0):\nRevenue grew 20%.", context)
        self.assertIn("[2] (Q3 Report, chunk 1):\nCosts fell 5%.", context)
        self.assertLess(context.index("[1]"), context.index("[2]"))

    def test_extract_citations_returns_cited_chunks_in_order(self):
        answer = "Costs fell [2], and revenue grew [1]."

        citations = citation_service.extract_citations(answer, self.chunks)

        self.assertEqual([c["chunk_number"] for c in citations], [0, 1])
        self.assertEqual(citations[0]["citation_number"], 1)
        self.assertEqual(citations[1]["citation_number"], 2)

    def test_extract_citations_dedups_repeated_markers(self):
        answer = "Revenue grew [1]. It really grew [1]!"

        citations = citation_service.extract_citations(answer, self.chunks)

        self.assertEqual(len(citations), 1)

    def test_extract_citations_drops_out_of_range_numbers(self):
        answer = "Revenue grew [1], allegedly per [99]."

        citations = citation_service.extract_citations(answer, self.chunks)

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["citation_number"], 1)

    def test_extract_citations_empty_for_uncited_answer(self):
        citations = citation_service.extract_citations("No markers here.", self.chunks)
        self.assertEqual(citations, [])

    def test_extract_citations_empty_for_no_answer_or_chunks(self):
        self.assertEqual(citation_service.extract_citations("", self.chunks), [])
        self.assertEqual(citation_service.extract_citations("[1]", []), [])


class LlmServiceTests(unittest.TestCase):
    """
    generate_answer() now returns a (answer, extras) tuple from a
    structured JSON-mode response (see llm_service.py's docstring),
    routed through the multi-provider llm_client.get_llm().generate()
    rather than a single-provider get_model()/generate_content() call.
    """

    def test_generate_answer_returns_stripped_model_text(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = '{"answer": "  The answer is 42 [1].  "}'

        with patch.object(llm_service, "get_llm", return_value=mock_llm):
            answer, extras = llm_service.generate_answer("[1] (Doc, chunk 0):\ncontext", "Q?")

        self.assertEqual(answer, "The answer is 42 [1].")

    def test_generate_answer_passes_configured_temperature(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = '{"answer": "answer"}'

        with patch.object(llm_service, "get_llm", return_value=mock_llm), \
             override_settings(ANSWER_TEMPERATURE=0.1):

            llm_service.generate_answer("context", "Q?")

        _, kwargs = mock_llm.generate.call_args
        self.assertEqual(kwargs["temperature"], 0.1)

    def test_generate_answer_returns_not_found_on_empty_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = ""

        with patch.object(llm_service, "get_llm", return_value=mock_llm):
            answer, extras = llm_service.generate_answer("context", "Q?")

        self.assertEqual(answer, prompt_templates.NOT_FOUND_ANSWER)

    def test_generate_answer_returns_service_unavailable_when_every_provider_fails(self):
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = llm_service.AllProvidersFailedError("boom")

        with patch.object(llm_service, "get_llm", return_value=mock_llm):
            answer, extras = llm_service.generate_answer("context", "Q?")

        self.assertEqual(answer, prompt_templates.SERVICE_UNAVAILABLE_ANSWER)

    def test_generate_answer_returns_not_found_on_unexpected_failure(self):
        with patch.object(llm_service, "get_llm", side_effect=RuntimeError("boom")):
            answer, extras = llm_service.generate_answer("context", "Q?")

        self.assertEqual(answer, prompt_templates.NOT_FOUND_ANSWER)


class RetrieveChunksOrchestrationTests(unittest.TestCase):
    """
    retrieve_chunks() feature-flag orchestration. All underlying
    retrieval sources (vector/bm25/graph/hyde/multi_query) are
    mocked, so this validates the wiring - which sources get called,
    with what arguments, and how results merge - without touching the
    database.
    """

    def setUp(self):
        # retrieve_chunks() caches its result per (question, user,
        # filters, top_k) - see retrieval_service.py -
        # process-wide/module-level, not per-test-isolated the way the
        # DB is for a django.test.TestCase. Several tests below reuse
        # the exact same "Who is the CEO?" question with no explicit
        # top_k, so without clearing here, whichever test happens to
        # run first "wins" and every later one silently gets its
        # mocked result back instead of exercising its own mocks.
        cache.clear()

        self.vector_result = [{"content": "v", "document": "D1", "chunk_number": 0, "score": 0.1, "search_type": "vector"}]
        self.bm25_result = [{"content": "b", "document": "D1", "chunk_number": 1, "score": 2.0, "search_type": "bm25"}]
        self.hyde_result = [{"content": "h", "document": "D2", "chunk_number": 0, "score": 0.2, "search_type": "hyde"}]
        self.mq_result = [{"content": "m", "document": "D3", "chunk_number": 0, "score": 0.03, "search_type": "multi_query"}]

    def test_default_flags_skip_hyde_and_multi_query(self):
        with patch.object(retrieval, "vector_search", return_value=self.vector_result), \
             patch.object(retrieval, "bm25_search", return_value=self.bm25_result) as m_bm25, \
             patch.object(retrieval, "graph_search", return_value=[]), \
             patch.object(retrieval, "hyde_search", return_value=self.hyde_result) as m_hyde, \
             patch("RAG.services.multi_query_service.multi_query_search", return_value=self.mq_result) as m_mq:

            results = retrieval.retrieve_chunks("Who is the CEO?")

        self.assertFalse(m_hyde.called)
        self.assertFalse(m_mq.called)
        self.assertEqual({r["search_type"] for r in results}, {"vector", "bm25"})
        # BM25 receives the raw question unchanged when expansion is off.
        self.assertEqual(m_bm25.call_args.args[0], "Who is the CEO?")

    @override_settings(ENABLE_HYDE=True, ENABLE_MULTI_QUERY=True, ENABLE_QUERY_EXPANSION=True)
    def test_enabling_all_flags_wires_every_source(self):
        with patch.object(retrieval, "vector_search", return_value=self.vector_result), \
             patch.object(retrieval, "bm25_search", return_value=self.bm25_result) as m_bm25, \
             patch.object(retrieval, "graph_search", return_value=[]), \
             patch.object(retrieval, "hyde_search", return_value=self.hyde_result) as m_hyde, \
             patch.object(retrieval, "expand_query", return_value="who is the ceo boss") as m_expand, \
             patch("RAG.services.multi_query_service.multi_query_search", return_value=self.mq_result) as m_mq:

            results = retrieval.retrieve_chunks("Who is the CEO?", top_k=10)

        self.assertTrue(m_hyde.called)
        self.assertTrue(m_mq.called)
        self.assertTrue(m_expand.called)
        self.assertEqual(
            {r["search_type"] for r in results},
            {"vector", "bm25", "hyde", "multi_query"},
        )
        # BM25 receives the expanded query text, not the raw question.
        self.assertEqual(m_bm25.call_args.args[0], "who is the ceo boss")

    def test_explicit_top_k_overrides_dynamic_sizing(self):
        with patch.object(retrieval, "vector_search", return_value=[]) as m_vec, \
             patch.object(retrieval, "bm25_search", return_value=[]) as m_bm25, \
             patch.object(retrieval, "graph_search", return_value=[]):

            retrieval.retrieve_chunks("Who is the CEO?", top_k=7)

        self.assertEqual(m_vec.call_args.kwargs["top_k"], 7)
        self.assertEqual(m_bm25.call_args.args[1], 7)

    @override_settings(ENABLE_DYNAMIC_TOP_K=False)
    def test_dynamic_top_k_disabled_uses_fixed_settings_top_k(self):
        from django.conf import settings as dj_settings

        with patch.object(retrieval, "vector_search", return_value=[]) as m_vec, \
             patch.object(retrieval, "bm25_search", return_value=[]), \
             patch.object(retrieval, "graph_search", return_value=[]):

            retrieval.retrieve_chunks(
                "What are the findings and risks and also the mitigations discussed?"
            )

        self.assertEqual(m_vec.call_args.kwargs["top_k"], dj_settings.TOP_K)

    def test_reranker_disabled_by_default_skips_rerank(self):
        with patch.object(retrieval, "vector_search", return_value=self.vector_result), \
             patch.object(retrieval, "bm25_search", return_value=self.bm25_result), \
             patch.object(retrieval, "graph_search", return_value=[]), \
             patch.object(retrieval, "rerank_chunks") as m_rerank:

            retrieval.retrieve_chunks("Who is the CEO?")

        self.assertFalse(m_rerank.called)

    @override_settings(ENABLE_RERANKER=True, RERANKER_CANDIDATE_MULTIPLIER=4)
    def test_reranker_enabled_over_fetches_and_delegates_final_result(self):
        with patch.object(retrieval, "vector_search", return_value=self.vector_result) as m_vec, \
             patch.object(retrieval, "bm25_search", return_value=self.bm25_result) as m_bm25, \
             patch.object(retrieval, "graph_search", return_value=[]) as m_graph, \
             patch.object(retrieval, "rerank_chunks", return_value=["reranked"]) as m_rerank:

            results = retrieval.retrieve_chunks("Who is the CEO?", top_k=3)

        # Candidate pool is over-fetched by RERANKER_CANDIDATE_MULTIPLIER
        # (3 * 4 = 12) so the reranker has real alternatives to reorder.
        self.assertEqual(m_vec.call_args.kwargs["top_k"], 12)
        self.assertEqual(m_bm25.call_args.args[1], 12)
        self.assertEqual(m_graph.call_args.args[2], 12)

        self.assertTrue(m_rerank.called)
        self.assertEqual(m_rerank.call_args.args[0], "Who is the CEO?")
        self.assertEqual(m_rerank.call_args.kwargs["top_k"], 3)
        self.assertEqual(results, ["reranked"])


class AnswerQuestionCompressionTests(unittest.TestCase):
    """
    answer_question()'s context-compression integration.
    retrieve_chunks() and generate_answer() are mocked, and `user`
    stays None so QueryLog.objects.create() is never reached, so this
    runs fully offline without a database.
    """

    def setUp(self):
        self.chunks = [
            {"content": "chunk a", "document": "D1", "chunk_number": 0, "score": 0.1, "search_type": "vector"},
            {"content": "chunk b", "document": "D1", "chunk_number": 1, "score": 0.2, "search_type": "vector"},
        ]

    def test_compression_disabled_by_default_skips_compress_context(self):
        with patch.object(query_service, "retrieve_chunks", return_value=self.chunks), \
             patch.object(query_service, "generate_answer", return_value=("the answer", {})) as m_answer, \
             patch.object(query_service, "compress_context") as m_compress:

            result = query_service.answer_question("Who is the CEO?")

        self.assertFalse(m_compress.called)
        self.assertEqual(result["sources"], self.chunks)
        context_arg = m_answer.call_args.args[0]
        self.assertIn("chunk a", context_arg)
        self.assertIn("chunk b", context_arg)

    @override_settings(ENABLE_CONTEXT_COMPRESSION=True)
    def test_compression_enabled_filters_before_context_is_built(self):
        compressed = [self.chunks[0]]

        with patch.object(query_service, "retrieve_chunks", return_value=self.chunks), \
             patch.object(query_service, "generate_answer", return_value=("the answer", {})) as m_answer, \
             patch.object(query_service, "compress_context", return_value=compressed) as m_compress:

            result = query_service.answer_question("Who is the CEO?")

        self.assertTrue(m_compress.called)
        self.assertEqual(m_compress.call_args.args[0], self.chunks)
        self.assertEqual(result["sources"], compressed)
        context_arg = m_answer.call_args.args[0]
        self.assertIn("chunk a", context_arg)
        self.assertNotIn("chunk b", context_arg)


class AnswerQuestionCitationTests(unittest.TestCase):
    """
    answer_question()'s Sprint 9 citation + confidence integration.
    retrieve_chunks() and generate_answer() are mocked, and `user`
    stays None so QueryLog.objects.create() is never reached, so this
    runs fully offline without a database.
    """

    def setUp(self):
        self.chunks = [
            {"content": "Revenue grew 20%.", "document": "Q3 Report", "chunk_number": 0, "score": 0.05, "search_type": "vector"},
            {"content": "Costs fell 5%.", "document": "Q3 Report", "chunk_number": 1, "score": 0.4, "search_type": "vector"},
        ]

    def test_cited_answer_populates_citations_and_marks_sources(self):
        with patch.object(query_service, "retrieve_chunks", return_value=self.chunks), \
             patch.object(query_service, "generate_answer", return_value=("Revenue grew 20% [1].", {})):

            result = query_service.answer_question("How did revenue change?")

        self.assertEqual(len(result["citations"]), 1)
        self.assertEqual(result["citations"][0]["chunk_number"], 0)
        self.assertEqual(result["sources"][0]["citation_number"], 1)
        self.assertNotIn("citation_number", result["sources"][1])

    def test_uncited_answer_discounts_confidence_relative_to_cited(self):
        with patch.object(query_service, "retrieve_chunks", return_value=self.chunks), \
             patch.object(query_service, "generate_answer", return_value=("Revenue grew 20% [1].", {})):

            cited_result = query_service.answer_question("How did revenue change?")

        with patch.object(query_service, "retrieve_chunks", return_value=self.chunks), \
             patch.object(query_service, "generate_answer", return_value=("Revenue grew, apparently.", {})):

            uncited_result = query_service.answer_question("How did revenue change?")

        self.assertEqual(uncited_result["citations"], [])
        self.assertLess(uncited_result["confidence"], cited_result["confidence"])

    def test_not_found_answer_yields_zero_confidence_and_no_citations(self):
        with patch.object(query_service, "retrieve_chunks", return_value=self.chunks), \
             patch.object(
                 query_service, "generate_answer", return_value=(prompt_templates.NOT_FOUND_ANSWER, {})
             ):

            result = query_service.answer_question("What is the capital of Mars?")

        self.assertEqual(result["confidence"], 0)
        self.assertEqual(result["citations"], [])


class HealthServiceTests(unittest.TestCase):
    """
    get_health_status() - get_system_status(), the background task pool
    check, and the LLM provider health checks are all mocked, so this
    runs offline regardless of whether a real database/LLM provider is
    reachable.
    """

    def setUp(self):
        # Every test in this class exercises DB/background-pool logic,
        # not LLM provider logic - default to "nothing configured" (an
        # empty dict short-circuits get_health_status()'s `if
        # llm_providers:` check) so these stay offline and each test's
        # pre-existing assertions are unaffected. See
        # LlmProviderHealthCheckTests below for coverage of this
        # check's own behavior.
        patcher = patch.object(health_service, "_check_llm_providers", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _system_status(self, db_online=True, pgvector_enabled=True, embeddings_complete=True):
        return {
            "db_online": db_online,
            "pgvector_enabled": pgvector_enabled,
            "embeddings_complete": embeddings_complete,
        }

    def _bg_jobs(self, available=True):
        return {"available": available, "max_workers": 4, "active": 0, "pending": 0}

    def test_ok_when_db_and_pgvector_and_background_pool_healthy(self):
        with patch.object(health_service, "get_system_status", return_value=self._system_status()), \
             patch.object(health_service, "_check_background_jobs", return_value=self._bg_jobs()):

            result = health_service.get_health_status()

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["checks"]["database"])
        self.assertTrue(result["checks"]["background_jobs"])

    def test_degraded_when_pgvector_disabled(self):
        with patch.object(
            health_service, "get_system_status",
            return_value=self._system_status(pgvector_enabled=False),
        ), patch.object(health_service, "_check_background_jobs", return_value=self._bg_jobs()):

            result = health_service.get_health_status()

        self.assertEqual(result["status"], "degraded")

    def test_degraded_when_background_pool_unavailable(self):
        with patch.object(health_service, "get_system_status", return_value=self._system_status()), \
             patch.object(health_service, "_check_background_jobs", return_value=self._bg_jobs(available=False)):

            result = health_service.get_health_status()

        self.assertEqual(result["status"], "degraded")
        self.assertFalse(result["checks"]["background_jobs"])

    def test_never_raises_when_system_status_blows_up(self):
        with patch.object(
            health_service, "get_system_status", side_effect=RuntimeError("db exploded")
        ), patch.object(health_service, "_check_background_jobs", return_value=self._bg_jobs()):

            result = health_service.get_health_status()

        self.assertEqual(result["status"], "degraded")
        self.assertFalse(result["checks"]["database"])


class LlmProviderHealthCheckTests(unittest.TestCase):
    """
    _check_llm_providers() and its fold-in to get_health_status()'s
    overall verdict - added alongside the performance/infra audit's
    ask_ai_stream/check_infra work ("all configured LLM providers
    before the application is considered healthy"). get_llm() and
    _is_configured() are both mocked, so this never makes a real
    provider network call.
    """

    def _system_status(self):
        return {"db_online": True, "pgvector_enabled": True, "embeddings_complete": True}

    def _bg_jobs(self):
        return {"available": True, "max_workers": 4, "active": 0, "pending": 0}

    def test_no_providers_configured_returns_empty_dict(self):
        with patch.object(health_service, "_is_configured", return_value=False):
            self.assertEqual(health_service._check_llm_providers(), {})

    def test_checks_only_configured_providers(self):
        mock_llm = MagicMock()
        mock_llm.health_check.side_effect = lambda provider: {"ok": provider == "openrouter", "latency_ms": 42, "message": "Connected"}

        with patch.object(health_service, "_is_configured", side_effect=lambda p: p in ("openrouter", "gemini")), \
             patch.object(health_service, "get_llm", return_value=mock_llm):

            result = health_service._check_llm_providers()

        self.assertEqual(result["openrouter"]["ok"], True)
        self.assertEqual(result["gemini"]["ok"], False)
        self.assertNotIn("groq", result)

    def test_provider_check_exception_reports_false_not_raise(self):
        mock_llm = MagicMock()
        mock_llm.health_check.side_effect = RuntimeError("boom")

        with patch.object(health_service, "_is_configured", return_value=True), \
             patch.object(health_service, "get_llm", return_value=mock_llm):

            result = health_service._check_llm_providers()

        self.assertTrue(result)
        self.assertTrue(all(entry["ok"] is False for entry in result.values()))

    def test_no_configured_providers_does_not_block_overall_health(self):
        with patch.object(health_service, "get_system_status", return_value=self._system_status()), \
             patch.object(health_service, "_check_background_jobs", return_value=self._bg_jobs()), \
             patch.object(health_service, "_check_llm_providers", return_value={}):

            result = health_service.get_health_status()

        self.assertEqual(result["status"], "ok")

    def test_at_least_one_healthy_provider_required_when_any_configured(self):
        # live_llm_check=True exercises _check_llm_providers() (mocked
        # below) - the default False path calls
        # _recent_llm_provider_status() instead (usage-derived, see
        # its own tests), but the "at least one must be healthy"
        # aggregation logic in get_health_status() is shared by both,
        # so testing it through either call is equally valid.
        with patch.object(health_service, "get_system_status", return_value=self._system_status()), \
             patch.object(health_service, "_check_background_jobs", return_value=self._bg_jobs()), \
             patch.object(health_service, "_check_llm_providers", return_value={
                 "openrouter": {"ok": False, "latency_ms": None, "message": "down"},
                 "gemini": {"ok": False, "latency_ms": None, "message": "down"},
             }):

            result = health_service.get_health_status(live_llm_check=True)

        self.assertEqual(result["status"], "degraded")

    def test_one_healthy_provider_among_several_keeps_overall_status_ok(self):
        healthy_providers = {
            "openrouter": {"ok": True, "latency_ms": 120, "message": "Connected"},
            "gemini": {"ok": False, "latency_ms": None, "message": "down"},
        }

        with patch.object(health_service, "get_system_status", return_value=self._system_status()), \
             patch.object(health_service, "_check_background_jobs", return_value=self._bg_jobs()), \
             patch.object(health_service, "_check_llm_providers", return_value=healthy_providers):

            result = health_service.get_health_status(live_llm_check=True)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["checks"]["llm_providers"], healthy_providers)

    def test_recent_provider_status_null_ok_does_not_block_overall_health(self):
        """A configured provider with zero recent traffic (ok=None) must not, by itself, drag the overall verdict to "degraded" - "no data" isn't "bad data". This is the default (live_llm_check=False) path."""

        with patch.object(health_service, "get_system_status", return_value=self._system_status()), \
             patch.object(health_service, "_check_background_jobs", return_value=self._bg_jobs()), \
             patch.object(health_service, "_recent_llm_provider_status", return_value={
                 "openrouter": {"ok": None, "latency_ms": None, "message": "No requests in the last 15 minutes - use Check Now for a live check."},
             }):

            result = health_service.get_health_status()

        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["live_llm_check"])


class LLMClientFallbackChainTests(unittest.TestCase):
    """
    LLMClient._build_chain() - pure function of settings + which
    provider API keys are configured, no network/DB. Locks in the
    guarantee _build_chain()'s own docstring promises ("never silently
    substitutes a different provider the admin didn't select"): with
    fallback disabled, a broken/unconfigured primary must fail rather
    than quietly trying Groq/Gemini/whichever other provider happens
    to have a key configured. This is the actual mechanism behind "AI
    Tasks must use the selected model, not silently use Gemini until
    it's explicitly selected" - the toggle already exists and already
    works; these tests are what verify that going forward.
    """

    @override_settings(LLM_PROVIDER="openrouter", LLM_FALLBACK_ENABLED=False,
                        OPENROUTER_API_KEY="key", GEMINI_API_KEY="key", GROQ_API_KEY="")
    def test_fallback_disabled_returns_only_the_primary(self):
        chain = llm_client.LLMClient()._build_chain()
        self.assertEqual(chain, ["openrouter"])

    @override_settings(LLM_PROVIDER="openrouter", LLM_FALLBACK_ENABLED=False,
                        OPENROUTER_API_KEY="", GEMINI_API_KEY="key", GROQ_API_KEY="key")
    def test_fallback_disabled_and_primary_unconfigured_returns_empty_chain(self):
        # Even though Gemini and Groq both have keys configured, a
        # disabled fallback must never substitute either of them for
        # an unconfigured primary - an empty chain (which
        # LLMClient.generate() turns into a clear AllProvidersFailedError)
        # is the correct outcome, not a silent switch to Gemini.
        chain = llm_client.LLMClient()._build_chain()
        self.assertEqual(chain, [])

    @override_settings(LLM_PROVIDER="openrouter", LLM_FALLBACK_ENABLED=True,
                        OPENROUTER_API_KEY="key", GEMINI_API_KEY="key", GROQ_API_KEY="")
    def test_fallback_enabled_appends_remaining_configured_providers_after_primary(self):
        chain = llm_client.LLMClient()._build_chain()
        self.assertEqual(chain, ["openrouter", "gemini"])

    @override_settings(LLM_PROVIDER="gemini", LLM_FALLBACK_ENABLED=True,
                        OPENROUTER_API_KEY="key", GEMINI_API_KEY="key", GROQ_API_KEY="key")
    def test_primary_is_not_duplicated_in_the_fallback_tail(self):
        chain = llm_client.LLMClient()._build_chain()
        self.assertEqual(chain, ["gemini", "groq", "openrouter"])

    @override_settings(LLM_PROVIDER="not_a_real_provider", LLM_FALLBACK_ENABLED=False,
                        OPENROUTER_API_KEY="key", GEMINI_API_KEY="key", GROQ_API_KEY="key")
    def test_unknown_primary_provider_is_ignored_not_substituted(self):
        chain = llm_client.LLMClient()._build_chain()
        self.assertEqual(chain, [])


class ProcessDocumentTaskTests(unittest.TestCase):
    """
    RAG.tasks.process_document_task - Document.objects.get() and
    process_uploaded_document() are mocked. Calling the task directly
    (not via task_runner.submit()) runs it synchronously with no thread
    pool required.
    """

    def test_processes_existing_document(self):
        mock_document = MagicMock(id=7)

        with patch.object(tasks.Document.objects, "get", return_value=mock_document) as m_get, \
             patch.object(tasks, "process_uploaded_document") as m_process:

            tasks.process_document_task(7)

        m_get.assert_called_once_with(id=7)
        m_process.assert_called_once_with(mock_document)

    def test_logs_and_returns_when_document_missing(self):
        with patch.object(
            tasks.Document.objects, "get", side_effect=tasks.Document.DoesNotExist
        ), patch.object(tasks, "process_uploaded_document") as m_process:

            result = tasks.process_document_task(999)

        self.assertIsNone(result)
        self.assertFalse(m_process.called)

    def test_retries_then_gives_up_without_raising(self):
        mock_document = MagicMock(id=7)

        with patch.object(tasks.Document.objects, "get", return_value=mock_document), \
             patch.object(
                 tasks, "process_uploaded_document", side_effect=RuntimeError("boom")
             ) as m_process, \
             patch.object(tasks.time, "sleep"):

            result = tasks.process_document_task(7)

        self.assertIsNone(result)
        self.assertEqual(m_process.call_count, tasks.MAX_PROCESSING_RETRIES)


class MaskEmailTests(unittest.TestCase):
    """RAG.utils.formatting.mask_email() - pure string logic, no DB."""

    def test_masks_middle_of_local_part(self):
        from .utils.formatting import mask_email
        self.assertEqual(mask_email("johndoe@example.com"), "j*****e@example.com")

    def test_short_local_part(self):
        from .utils.formatting import mask_email
        self.assertEqual(mask_email("ab@example.com"), "a*@example.com")

    def test_single_char_local_part(self):
        from .utils.formatting import mask_email
        self.assertEqual(mask_email("a@example.com"), "a*@example.com")

    def test_empty_or_invalid_input(self):
        from .utils.formatting import mask_email
        self.assertEqual(mask_email(""), "")
        self.assertEqual(mask_email(None), "")
        self.assertEqual(mask_email("not-an-email"), "not-an-email")


class OtpCodeHashRoundTripTests(unittest.TestCase):
    """
    otp_service generates a code and stores only make_password(code) -
    confirms check_password() round-trips correctly and a wrong code
    never matches. No DB needed, just Django's password hasher.
    """

    def test_generated_code_is_six_digits(self):
        from .services.otp_service import _generate_code, OTP_LENGTH
        code = _generate_code()
        self.assertEqual(len(code), OTP_LENGTH)
        self.assertTrue(code.isdigit())

    def test_hash_round_trip(self):
        from django.contrib.auth.hashers import check_password, make_password
        from .services.otp_service import _generate_code

        code = _generate_code()
        hashed = make_password(code)

        self.assertNotEqual(hashed, code)  # never stored in plaintext
        self.assertTrue(check_password(code, hashed))
        self.assertFalse(check_password("000000" if code != "000000" else "111111", hashed))


class RateLimitServiceTests(unittest.TestCase):
    """Fixed-window counter logic against the real (LocMemCache-backed) Django cache - no DB needed."""

    def setUp(self):
        cache.clear()

    def test_allows_up_to_limit_then_blocks(self):
        from .services.rate_limit_service import is_rate_limited

        key = "test:allows_up_to_limit"
        for _ in range(3):
            self.assertFalse(is_rate_limited(key, limit=3, window_seconds=60))
        self.assertTrue(is_rate_limited(key, limit=3, window_seconds=60))

    def test_independent_keys_dont_interfere(self):
        from .services.rate_limit_service import is_rate_limited

        for _ in range(3):
            is_rate_limited("test:key_a", limit=3, window_seconds=60)

        self.assertFalse(is_rate_limited("test:key_b", limit=3, window_seconds=60))

    def test_cooldown_starts_and_reports_remaining(self):
        from .services.rate_limit_service import get_cooldown_remaining_seconds, start_cooldown

        key = "test:cooldown"
        self.assertEqual(get_cooldown_remaining_seconds(key), 0)
        start_cooldown(key, 60)
        remaining = get_cooldown_remaining_seconds(key)
        self.assertTrue(0 < remaining <= 60)


class NotificationServiceTests(TestCase):
    """create_notification()/mark_read()/mark_all_read()/get_unread_count() against a real test DB."""

    def setUp(self):
        cache.clear()
        self.recipient = User.objects.create_user(username="notif_recipient", password="pw", email="recipient@example.com")
        self.actor = User.objects.create_user(username="notif_actor", password="pw")

    def test_create_notification_creates_row(self):
        from .services.notification_service import create_notification

        notification = create_notification(
            recipient=self.recipient, actor=self.actor, notification_type="document.shared",
            title="Test", message="Test message", send_email=False,
        )
        self.assertIsNotNone(notification)
        self.assertEqual(Notification.objects.filter(recipient=self.recipient).count(), 1)
        self.assertFalse(notification.is_read)

    def test_create_notification_never_raises_for_invalid_recipient(self):
        from .services.notification_service import create_notification

        result = create_notification(
            recipient=None, notification_type="document.shared", title="T", message="M",
        )
        self.assertIsNone(result)

    def test_mark_read_is_ownership_scoped(self):
        from .services.notification_service import mark_read

        notification = Notification.objects.create(
            recipient=self.recipient, notification_type="document.shared", title="T", message="M",
        )
        other_user = User.objects.create_user(username="notif_other", password="pw")

        self.assertFalse(mark_read(notification.id, other_user))
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

        self.assertTrue(mark_read(notification.id, self.recipient))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_all_read_and_unread_count(self):
        from .services.notification_service import get_unread_count, mark_all_read

        for i in range(3):
            Notification.objects.create(recipient=self.recipient, notification_type="document.shared", title=f"T{i}", message="M")

        self.assertEqual(get_unread_count(self.recipient), 3)
        marked = mark_all_read(self.recipient)
        self.assertEqual(marked, 3)
        self.assertEqual(get_unread_count(self.recipient), 0)


class DocumentShareConstraintTests(TestCase):
    """
    DocumentShare's 3-way exactly-one-target CheckConstraint and the
    partial (invited_email-only) UniqueConstraint added for invite-by-
    email sharing (Phase 7) - regression coverage for the bug where a
    plain unique_together on invited_email collided across every
    ordinary (blank-invited_email) share on the same document.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="share_owner", password="pw")
        self.other = User.objects.create_user(username="share_other", password="pw")
        self.document = Document.objects.create(user=self.owner, title="Doc", file="documents/test.txt")

    def test_two_ordinary_shares_on_same_document_do_not_collide(self):
        """Regression: both blank invited_email - must NOT trip the partial unique constraint."""

        DocumentShare.objects.create(document=self.document, shared_with_user=self.other, shared_by=self.owner)

        third = User.objects.create_user(username="share_third", password="pw")
        role_share = DocumentShare.objects.create(document=self.document, invited_email="pending@example.com", shared_by=self.owner)

        self.assertEqual(DocumentShare.objects.filter(document=self.document).count(), 2)

    def test_duplicate_pending_invite_rejected_at_db_level(self):
        DocumentShare.objects.create(document=self.document, invited_email="dup@example.com", shared_by=self.owner)

        with self.assertRaises(Exception):
            DocumentShare.objects.create(document=self.document, invited_email="dup@example.com", shared_by=self.owner)

    def test_create_share_email_branch_creates_pending_invite(self):
        from .services.sharing_service import create_share

        share = create_share(self.document, self.owner, "email", "invitee@example.com")
        self.assertEqual(share.invited_email, "invitee@example.com")
        self.assertIsNone(share.shared_with_user)

    def test_create_share_email_branch_resolves_to_existing_user(self):
        from .services.sharing_service import create_share

        existing = User.objects.create_user(username="already_here", password="pw", email="already@example.com")
        share = create_share(self.document, self.owner, "email", "already@example.com")
        self.assertEqual(share.shared_with_user_id, existing.id)
        self.assertEqual(share.invited_email, "")


class OtpInviteConversionTests(TestCase):
    """otp_service.verify_otp() converting a pending DocumentShare.invited_email into a real share on successful verification (Phase 7)."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username="convert_owner", password="pw")
        self.document = Document.objects.create(user=self.owner, title="Doc", file="documents/test.txt")
        self.invitee = User.objects.create_user(
            username="convert_invitee", password="pw", email="convertme@example.com", is_active=False,
        )
        self.share = DocumentShare.objects.create(
            document=self.document, invited_email="convertme@example.com", shared_by=self.owner,
        )

    def test_verify_otp_converts_pending_invite_and_notifies(self):
        from .services import otp_service

        otp_service.generate_and_send_otp(self.invitee)
        otp = self.invitee.email_otps.filter(is_used=False).latest("created_at")

        # Recover the raw code the same way the real flow would never
        # need to (it only ever exists in-memory/in the email) - here
        # we bypass by generating our own OTP row directly instead of
        # trying to intercept the background-emailed code.
        from django.contrib.auth.hashers import make_password
        raw_code = "123456"
        otp.code_hash = make_password(raw_code)
        otp.save(update_fields=["code_hash"])

        success, status = otp_service.verify_otp(self.invitee, raw_code)

        self.assertTrue(success)
        self.assertEqual(status, "")

        self.share.refresh_from_db()
        self.assertEqual(self.share.shared_with_user_id, self.invitee.id)
        self.assertEqual(self.share.invited_email, "")

        self.assertTrue(
            Notification.objects.filter(recipient=self.invitee, notification_type="document.shared").exists()
        )


class ExecuteRunStatusTests(TestCase):
    """
    ai_tasks_engine_service.execute_run()'s COMPLETED vs FAILED
    decision. Added as a regression test: a run where every single
    item failed used to still be marked COMPLETED (with only a
    best-effort note in error_message), so a run that produced zero
    real results - e.g. every configured LLM provider down or
    misconfigured - still surfaced as "AI Task completed" instead of
    "AI Task failed". get_document_context_text() and _call_llm_json()
    are both mocked so this never touches the filesystem or a real LLM
    provider.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="ai_tasks_tester", password="pw")
        self.doc_a = Document.objects.create(user=self.user, title="Doc A", file="documents/a.txt")
        self.doc_b = Document.objects.create(user=self.user, title="Doc B", file="documents/b.txt")

    def _make_run(self):
        run = AITaskRun.objects.create(user=self.user, task_type=AITaskRun.TaskType.SUMMARIZE, config={})
        AITaskRunDocument.objects.create(run=run, document=self.doc_a, role=AITaskRunDocument.Role.TARGET)
        AITaskRunDocument.objects.create(run=run, document=self.doc_b, role=AITaskRunDocument.Role.TARGET)
        return run

    def test_run_marked_failed_when_every_item_fails(self):
        run = self._make_run()

        with patch.object(ai_tasks_engine, "get_document_context_text", return_value={"text": "some content"}), \
             patch.object(ai_tasks_engine, "_call_llm_json", return_value=None):
            ai_tasks_engine.execute_run(run)

        run.refresh_from_db()
        self.assertEqual(run.status, AITaskRun.Status.FAILED)
        self.assertIn("2", run.error_message)
        self.assertEqual(
            run.results.filter(document__isnull=False, data__error=True).count(), 2
        )

    def test_run_marked_completed_with_a_partial_failure(self):
        run = self._make_run()
        success = {"summary": "ok", "key_points": [], "topics": []}

        with patch.object(ai_tasks_engine, "get_document_context_text", return_value={"text": "some content"}), \
             patch.object(ai_tasks_engine, "_call_llm_json", side_effect=[success, None]):
            ai_tasks_engine.execute_run(run)

        run.refresh_from_db()
        self.assertEqual(run.status, AITaskRun.Status.COMPLETED)
        self.assertIn("1 of 2", run.error_message)

    def test_run_marked_completed_when_everything_succeeds(self):
        run = self._make_run()
        success = {"summary": "ok", "key_points": [], "topics": []}

        with patch.object(ai_tasks_engine, "get_document_context_text", return_value={"text": "some content"}), \
             patch.object(ai_tasks_engine, "_call_llm_json", return_value=success):
            ai_tasks_engine.execute_run(run)

        run.refresh_from_db()
        self.assertEqual(run.status, AITaskRun.Status.COMPLETED)
        self.assertEqual(run.error_message, "")
