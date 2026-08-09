"""
AI Tasks generic engine.

execute_run(run) is the top-level, never-raise entry point (mirrors
graph_extraction_service.extract_graph()'s contract) - it sets
status=RUNNING, dispatches to the matching _run_<task_type> handler,
and always ends by setting status (COMPLETED/FAILED) + completed_at,
so RAG.tasks.run_ai_task's Celery wrapper never needs its own
try/except around business logic.

Every per-item LLM call goes through _call_llm_json(), which never
raises - on failure it logs and returns None, and the caller writes a
degraded-but-present AITaskResult row (_write_failed_result) rather
than aborting the whole batch. One bad LLM call must never lose every
other document's already-computed result in a run of up to
settings.AI_TASKS_MAX_DOCUMENTS documents.

Context building reuses text_extractor.extract_text() directly (not
preview_service.py, which is a UI-preview concern with a hardcoded
10k-char budget - AI Tasks need substantially more of each document).
Citations reuse citation_service.build_cited_context() verbatim - one
"chunk" per document (chunk_number is always 1: AI Tasks cite whole
documents, not sub-chunks, a deliberate reuse of the existing shape,
not a new citation convention).
"""

import logging
import re

from django.utils import timezone

from ..models import AITaskResult, AITaskRun
from .ai_tasks_prompts import (
    build_analyze_prompt,
    build_analyze_synthesis_prompt,
    build_cluster_label_prompt,
    build_compare_prompt,
    build_executive_summary_prompt,
    build_extract_prompt,
    build_report_extract_prompt,
    build_report_synthesis_prompt,
    build_summarize_prompt,
    build_validate_prompt,
)
from .ai_tasks_similarity_service import (
    DEFAULT_SIMILARITY_THRESHOLD,
    build_document_embedding,
    cluster_documents,
    similarity_to_centroid,
    split_into_groups,
)
from .citation_service import build_cited_context
from .llm_client import generate_json
from .perf import timed_stage
from .text_extractor import extract_text

logger = logging.getLogger(__name__)

MAX_DOCUMENT_CONTEXT_CHARS = 40000  # ~10k tokens/doc - keeps a 100-doc batch's
                                     # total prompt size bounded without a
                                     # tokenizer dependency; truncated, not
                                     # errored, for outliers.

FAILED_ITEM_SUMMARY = "This item could not be analyzed - the AI service returned an error."

CITATION_NUMBER_PATTERN = re.compile(r"\[(\d+)\]")


# ============================================================
# Context building
# ============================================================

def get_document_context_text(document, max_chars=MAX_DOCUMENT_CONTEXT_CHARS):
    """
    Never-raise text extraction for AI Task context - same contract as
    preview_service.get_document_preview_text() (extract_text wrapped
    in try/except) but with a much larger default budget. Returns
    {"text": ..., "truncated": bool} or {"error": "..."}.
    """

    if not document.file:
        return {"error": "This document has no file to read."}

    with timed_stage("AI Task context extraction", document_id=document.id):

        try:
            text = extract_text(document.file.path)
        except Exception:
            logger.exception("AI Tasks context extraction failed for document %s", document.id)
            return {"error": "Couldn't extract text from this document."}

        text = (text or "").strip()

        if not text:
            return {"error": "This document has no extractable text."}

        truncated = len(text) > max_chars

    return {"text": text[:max_chars], "truncated": truncated}


def _source_block(document, text, role="target"):
    return {"document": document.title, "chunk_number": 1, "content": text, "role": role}


# ============================================================
# LLM call + citation helpers shared by every task handler
# ============================================================

def _call_llm_json(run, prompt, item_label):
    """
    Never-raise JSON-mode call - the one place every per-item handler
    below calls the LLM. Delegates to llm_client.generate_json(), the
    same JSON-mode call+parse+validate helper this function was
    originally extracted from - Ask AI's structured answer
    (llm_service.generate_answer()) now goes through the shared one
    instead of AI Tasks having its own copy. Returns a parsed dict on
    success, or None on any failure (network error, empty response,
    malformed JSON, non-dict payload) - logged in every failure case,
    never raised. Wrapped in timed_stage() so every one of the ~15 call
    sites across the 8 task handlers gets recorded into the run's
    AIRequestTrace with no per-call-site change needed.
    """

    with timed_stage("AI Task LLM call", item=item_label):
        return generate_json(prompt, temperature=0.2, context_label=f"AI Task run {run.id}: {item_label}")


def _collect_citation_numbers(value, found=None):
    """
    Recursively walks a parsed JSON payload collecting every citation
    reference the model produced, regardless of which of the two
    conventions the schema used: an explicit integer "citation" key
    (structured items - findings/violations/relevant_points/...), or
    an inline "[n]" marker inside a prose string (summary/narrative
    fields) - the same [n] convention citation_service.py uses for
    Ask AI. Works generically across all 8 task schemas without
    needing task-specific citation-collection code.
    """

    if found is None:
        found = []

    if isinstance(value, dict):
        for key, val in value.items():
            if key == "citation" and isinstance(val, int):
                found.append(val)
            else:
                _collect_citation_numbers(val, found)
    elif isinstance(value, list):
        for item in value:
            _collect_citation_numbers(item, found)
    elif isinstance(value, str):
        found.extend(int(match) for match in CITATION_NUMBER_PATTERN.findall(value))

    return found


def _citations_from_data(data, source_chunks):
    """Resolves every citation number _collect_citation_numbers() finds in `data` against `source_chunks` (build_cited_context()'s input list), dropping out-of-range/invented numbers - same tolerance citation_service.extract_citations() has for Ask AI."""

    numbers = sorted(set(_collect_citation_numbers(data)))

    citations = []

    for number in numbers:
        if not (1 <= number <= len(source_chunks)):
            continue
        chunk = source_chunks[number - 1]
        citations.append({
            "number": number,
            "document": chunk["document"],
            "chunk_number": chunk["chunk_number"],
            "role": chunk.get("role", "target"),
        })

    return citations


def _write_failed_result(run, document=None, title=""):
    return AITaskResult.objects.create(
        run=run,
        document=document,
        title=title or (document.title if document else ""),
        summary=FAILED_ITEM_SUMMARY,
        data={"error": True},
    )


def _budget_per_document(count):
    """Divides the per-run context budget across N documents so a Compare/Validate batch call's total prompt size stays bounded regardless of N."""

    return max(MAX_DOCUMENT_CONTEXT_CHARS // max(count, 1), 2000)


# ============================================================
# Analyze Documents
# ============================================================

def _run_analyze(run, targets, references):
    criteria = run.config.get("criteria", "")
    scored = []  # [(document, score, AITaskResult)] for the synthesis pass

    for document in targets:
        context_result = get_document_context_text(document)

        if "error" in context_result:
            _write_failed_result(run, document=document)
            continue

        source_chunks = [_source_block(document, context_result["text"])]
        context = build_cited_context(source_chunks)
        prompt = build_analyze_prompt(context, criteria)
        parsed = _call_llm_json(run, prompt, f"analyze document {document.id}")

        if parsed is None:
            _write_failed_result(run, document=document)
            continue

        score = parsed.get("score")
        score = float(score) if isinstance(score, (int, float)) else None

        result = AITaskResult.objects.create(
            run=run,
            document=document,
            score=score,
            title=document.title,
            summary=parsed.get("summary", ""),
            data={
                "findings": parsed.get("findings", []),
                "missing_requirements": parsed.get("missing_requirements", []),
            },
            citations=_citations_from_data(parsed, source_chunks),
        )

        if score is not None:
            scored.append((document, score, result))

    # Assign rank in Python by sorting already-computed scores - no extra LLM call needed.
    scored.sort(key=lambda item: item[1], reverse=True)
    for index, (_, _, result) in enumerate(scored, start=1):
        result.rank = index
        result.save(update_fields=["rank"])

    if not scored:
        return

    results_text = "\n".join(
        f"- {document.title}: score {score}, {result.summary}"
        for document, score, result in scored
    )
    synthesis_prompt = build_analyze_synthesis_prompt(results_text, len(scored))
    synthesis = _call_llm_json(run, synthesis_prompt, "analyze synthesis")

    if synthesis is not None:
        AITaskResult.objects.create(
            run=run,
            title="Ranking Summary",
            summary=synthesis.get("narrative", ""),
            data={"common_gaps": synthesis.get("common_gaps", [])},
        )


# ============================================================
# Compare Documents
# ============================================================

def _run_compare(run, targets, references):
    per_doc_budget = _budget_per_document(len(targets))
    source_chunks = []
    included_documents = []

    for document in targets:
        context_result = get_document_context_text(document, max_chars=per_doc_budget)
        if "error" in context_result:
            _write_failed_result(run, document=document)
            continue
        included_documents.append(document)
        source_chunks.append(_source_block(document, context_result["text"]))

    if len(source_chunks) < 2:
        # Nothing meaningful to compare - the per-document failure rows
        # above already explain why, no corpus-level call is made.
        return

    context = build_cited_context(source_chunks)
    prompt = build_compare_prompt(context)
    parsed = _call_llm_json(run, prompt, "compare batch")

    if parsed is None:
        run.error_message = "The comparison could not be completed - the AI service returned an error."
        return

    citations = _citations_from_data(parsed, source_chunks)

    AITaskResult.objects.create(
        run=run,
        title="Comparison",
        summary=parsed.get("overall_narrative", ""),
        data={"dimensions": parsed.get("dimensions", [])},
        citations=citations,
    )

    titles_to_documents = {document.title: document for document in included_documents}

    for entry in parsed.get("per_document", []):
        if not isinstance(entry, dict):
            continue
        document = titles_to_documents.get(entry.get("document"))
        if document is None:
            continue
        AITaskResult.objects.create(
            run=run,
            document=document,
            title=document.title,
            summary=entry.get("position", ""),
            citations=_citations_from_data(entry, source_chunks),
        )


# ============================================================
# Summarize Documents
# ============================================================

def _run_summarize(run, targets, references):
    length = run.config.get("length", "3-5 sentences")
    summaries = []

    for document in targets:
        context_result = get_document_context_text(document)
        if "error" in context_result:
            _write_failed_result(run, document=document)
            continue

        source_chunks = [_source_block(document, context_result["text"])]
        prompt = build_summarize_prompt(build_cited_context(source_chunks), length)
        parsed = _call_llm_json(run, prompt, f"summarize document {document.id}")

        if parsed is None:
            _write_failed_result(run, document=document)
            continue

        summary_text = parsed.get("summary", "")

        AITaskResult.objects.create(
            run=run,
            document=document,
            title=document.title,
            summary=summary_text,
            data={"key_points": parsed.get("key_points", []), "topics": parsed.get("topics", [])},
            citations=_citations_from_data(parsed, source_chunks),
        )

        summaries.append((document, summary_text))

    if len(summaries) <= 1:
        return

    combined = "\n\n".join(f"{document.title}: {summary}" for document, summary in summaries)
    synthesis = _call_llm_json(run, build_executive_summary_prompt(combined, len(summaries)), "executive summary")

    if synthesis is not None:
        AITaskResult.objects.create(
            run=run,
            title="Executive Summary",
            summary=synthesis.get("executive_summary", ""),
            data={"common_topics": synthesis.get("common_topics", [])},
        )


# ============================================================
# Extract Information
# ============================================================

def _run_extract(run, targets, references):
    fields = run.config.get("fields") or []
    table = {}

    for document in targets:
        context_result = get_document_context_text(document)
        if "error" in context_result:
            _write_failed_result(run, document=document)
            continue

        source_chunks = [_source_block(document, context_result["text"])]
        prompt = build_extract_prompt(build_cited_context(source_chunks), fields)
        parsed = _call_llm_json(run, prompt, f"extract document {document.id}")

        if parsed is None:
            _write_failed_result(run, document=document)
            continue

        extracted_fields = parsed.get("fields", {})

        AITaskResult.objects.create(
            run=run,
            document=document,
            title=document.title,
            data={"fields": extracted_fields},
            citations=_citations_from_data(parsed, source_chunks),
        )

        table[document.title] = extracted_fields

    if table:
        AITaskResult.objects.create(
            run=run,
            title="Combined Table",
            data={"table": table},
        )


# ============================================================
# Validate Against Reference Documents
# ============================================================

def _run_validate(run, targets, references):
    reference_budget = _budget_per_document(len(references) + 1)
    reference_chunks = []

    for reference in references:
        context_result = get_document_context_text(reference, max_chars=reference_budget)
        if "error" not in context_result:
            reference_chunks.append(_source_block(reference, context_result["text"], role="reference"))

    scores = []

    for document in targets:
        context_result = get_document_context_text(document, max_chars=reference_budget)
        if "error" in context_result:
            _write_failed_result(run, document=document)
            continue

        source_chunks = reference_chunks + [_source_block(document, context_result["text"])]
        prompt = build_validate_prompt(build_cited_context(source_chunks))
        parsed = _call_llm_json(run, prompt, f"validate document {document.id}")

        if parsed is None:
            _write_failed_result(run, document=document)
            continue

        score = parsed.get("compliance_score")
        score = float(score) if isinstance(score, (int, float)) else None

        AITaskResult.objects.create(
            run=run,
            document=document,
            score=score,
            title=document.title,
            summary=parsed.get("summary", ""),
            data={
                "violations": parsed.get("violations", []),
                "compliant_points": parsed.get("compliant_points", []),
            },
            citations=_citations_from_data(parsed, source_chunks),
        )

        if score is not None:
            scores.append(score)

    if scores:
        AITaskResult.objects.create(
            run=run,
            title="Compliance Overview",
            summary=f"{len(scores)} of {len(targets)} target document(s) validated. Average compliance score: {round(sum(scores) / len(scores))}.",
            data={"average_score": round(sum(scores) / len(scores), 1), "validated_count": len(scores)},
        )


# ============================================================
# Find Similar Documents / Organize Documents
# (embedding-based - see ai_tasks_similarity_service.py)
# ============================================================

def _embed_targets(run, targets):
    """Shared by Find Similar / Organize - returns (ids, embeddings) parallel lists for documents that already have ChunkEmbedding rows, writing a 'not processed yet' result for any that don't."""

    ids, embeddings = [], []

    for document in targets:
        embedding = build_document_embedding(document)
        if embedding is None:
            AITaskResult.objects.create(
                run=run,
                document=document,
                title=document.title,
                summary="This document hasn't been processed yet - click Embed on it in My Documents first.",
                data={"error": "not_embedded"},
            )
            continue
        ids.append(document.id)
        embeddings.append(embedding)

    return ids, embeddings


def _label_group(run, member_documents):
    excerpts = "\n\n".join(
        f"{document.title}: {get_document_context_text(document, max_chars=1500).get('text', '')}"
        for document in member_documents[:3]
    )
    return _call_llm_json(run, build_cluster_label_prompt(excerpts), "group label")


def _run_find_similar(run, targets, references):
    documents_by_id = {document.id: document for document in targets}
    ids, embeddings = _embed_targets(run, targets)

    threshold = run.config.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        threshold = DEFAULT_SIMILARITY_THRESHOLD

    clusters = cluster_documents(ids, embeddings, threshold=threshold)
    clustered_ids = {doc_id for cluster in clusters for doc_id in cluster["document_ids"]}

    embedding_by_id = dict(zip(ids, embeddings))

    for index, cluster in enumerate(clusters, start=1):
        member_documents = [documents_by_id[doc_id] for doc_id in cluster["document_ids"]]
        label_data = _label_group(run, member_documents)
        label = label_data.get("label", f"Similar Group {index}") if label_data else f"Similar Group {index}"
        explanation = label_data.get("explanation", "") if label_data else ""

        AITaskResult.objects.create(
            run=run,
            rank=index,
            title=label,
            summary=explanation,
            data={"member_document_ids": cluster["document_ids"], "member_count": len(cluster["document_ids"])},
        )

        for doc_id in cluster["document_ids"]:
            AITaskResult.objects.create(
                run=run,
                document=documents_by_id[doc_id],
                rank=index,
                score=similarity_to_centroid(embedding_by_id[doc_id], cluster["centroid"]),
                title=documents_by_id[doc_id].title,
                data={"cluster_label": label},
            )

    for doc_id in ids:
        if doc_id not in clustered_ids:
            AITaskResult.objects.create(
                run=run,
                document=documents_by_id[doc_id],
                title=documents_by_id[doc_id].title,
                summary="No similar documents found above the similarity threshold.",
                data={"cluster_label": None},
            )


def _run_organize(run, targets, references):
    documents_by_id = {document.id: document for document in targets}
    ids, embeddings = _embed_targets(run, targets)

    if not ids:
        return

    target_groups = run.config.get("target_groups")
    embedding_by_id = dict(zip(ids, embeddings))

    if target_groups:
        try:
            groups = split_into_groups(ids, embeddings, int(target_groups))
        except (TypeError, ValueError):
            groups = split_into_groups(ids, embeddings, max(1, len(ids) // 5))
        leftover_ids = []
    else:
        threshold = run.config.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            threshold = DEFAULT_SIMILARITY_THRESHOLD
        groups = cluster_documents(ids, embeddings, threshold=threshold)
        clustered_ids = {doc_id for group in groups for doc_id in group["document_ids"]}
        leftover_ids = [doc_id for doc_id in ids if doc_id not in clustered_ids]

    for index, group in enumerate(groups, start=1):
        member_documents = [documents_by_id[doc_id] for doc_id in group["document_ids"]]
        label_data = _label_group(run, member_documents) if len(member_documents) > 1 else None
        label = label_data.get("label", f"Group {index}") if label_data else (member_documents[0].title if len(member_documents) == 1 else f"Group {index}")
        explanation = label_data.get("explanation", "") if label_data else ""

        AITaskResult.objects.create(
            run=run, rank=index, title=label, summary=explanation,
            data={"member_document_ids": group["document_ids"], "member_count": len(group["document_ids"])},
        )

        for doc_id in group["document_ids"]:
            AITaskResult.objects.create(
                run=run, document=documents_by_id[doc_id], rank=index,
                score=similarity_to_centroid(embedding_by_id[doc_id], group["centroid"]),
                title=documents_by_id[doc_id].title, data={"cluster_label": label},
            )

    if leftover_ids:
        AITaskResult.objects.create(
            run=run, rank=len(groups) + 1, title="Other",
            summary="Documents that didn't closely match another document.",
            data={"member_document_ids": leftover_ids, "member_count": len(leftover_ids)},
        )
        for doc_id in leftover_ids:
            AITaskResult.objects.create(
                run=run, document=documents_by_id[doc_id], rank=len(groups) + 1,
                title=documents_by_id[doc_id].title, data={"cluster_label": "Other"},
            )


# ============================================================
# Generate Reports
# ============================================================

def _run_report(run, targets, references):
    focus = run.config.get("focus", "")
    title = run.config.get("title", "Generated Report")

    extracts = []  # [(document, [relevant_points])]

    for document in targets:
        context_result = get_document_context_text(document)
        if "error" in context_result:
            _write_failed_result(run, document=document)
            continue

        source_chunks = [_source_block(document, context_result["text"])]
        prompt = build_report_extract_prompt(build_cited_context(source_chunks), focus)
        parsed = _call_llm_json(run, prompt, f"report extract document {document.id}")

        if parsed is None:
            _write_failed_result(run, document=document)
            continue

        points = parsed.get("relevant_points", [])

        AITaskResult.objects.create(
            run=run,
            document=document,
            title=document.title,
            data={"relevant_points": points},
            citations=_citations_from_data(parsed, source_chunks),
        )

        if points:
            extracts.append((document, points))

    if not extracts:
        return

    extracts_text = "\n\n".join(
        f"From {document.title}:\n" + "\n".join(f"- {point.get('point', '')} [{point.get('citation', '?')}]" for point in points if isinstance(point, dict))
        for document, points in extracts
    )

    synthesis_prompt = build_report_synthesis_prompt(extracts_text, len(extracts), title, focus)
    synthesis = _call_llm_json(run, synthesis_prompt, "report synthesis")

    if synthesis is not None:
        AITaskResult.objects.create(
            run=run,
            title=synthesis.get("title", title),
            summary=synthesis.get("executive_summary", ""),
            data={"sections": synthesis.get("sections", [])},
        )
    else:
        run.error_message = "The final report could not be synthesized - the AI service returned an error."


# ============================================================
# Top-level dispatch
# ============================================================

_HANDLERS = {
    AITaskRun.TaskType.ANALYZE: _run_analyze,
    AITaskRun.TaskType.COMPARE: _run_compare,
    AITaskRun.TaskType.SUMMARIZE: _run_summarize,
    AITaskRun.TaskType.EXTRACT: _run_extract,
    AITaskRun.TaskType.VALIDATE: _run_validate,
    AITaskRun.TaskType.FIND_SIMILAR: _run_find_similar,
    AITaskRun.TaskType.ORGANIZE: _run_organize,
    AITaskRun.TaskType.REPORT: _run_report,
}


def execute_run(run):
    """
    Never-raise top-level entry point (mirrors
    graph_extraction_service.extract_graph()'s contract) - called by
    RAG.tasks.run_ai_task inside a Celery worker. Always ends by
    setting run.status (COMPLETED or FAILED) + completed_at, so the
    Celery task itself needs no try/except around business logic.

    status=FAILED is reserved for a run-level exception outside any
    per-item try/except (e.g. the run's own document set failing to
    load) - a per-item LLM failure never fails the whole run, it just
    yields a degraded AITaskResult row for that one item (see
    _write_failed_result / _call_llm_json's never-raise contract).
    """

    run.status = AITaskRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])

    try:
        run_documents = list(run.run_documents.select_related("document").all())
        targets = [rd.document for rd in run_documents if rd.role == "target"]
        references = [rd.document for rd in run_documents if rd.role == "reference"]

        handler = _HANDLERS.get(run.task_type)
        if handler is None:
            raise ValueError(f"Unknown AI Task type: {run.task_type}")

        with timed_stage("AI Task run TOTAL", task_type=run.task_type, documents=len(targets)):
            handler(run, targets, references)

        total_items = run.results.filter(document__isnull=False).count()
        failed_items = run.results.filter(document__isnull=False, data__error=True).count()

        if failed_items and total_items:
            run.error_message = (run.error_message + " " if run.error_message else "") + f"{failed_items} of {total_items} document(s) could not be analyzed."

        run.status = AITaskRun.Status.COMPLETED

    except Exception:
        logger.exception("AI Task run %s failed", run.id)
        run.status = AITaskRun.Status.FAILED
        run.error_message = run.error_message or "This run failed unexpectedly - check the server logs."

    run.completed_at = timezone.now()
    run.save(update_fields=["status", "error_message", "completed_at"])
