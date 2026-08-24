"""
AI Tasks prompt templates.

One `.format()` template + `build_..._prompt()` pair per task-type
LLM call, following the exact structural precedent
prompt_templates.py established for Ask AI: numbered grounding rules,
an inline JSON schema example, and a "[n]" inline-citation instruction
against a citation_service.build_cited_context()-built numbered source
list.

IMPORTANT: every literal `{`/`}` inside a JSON schema example below
must be doubled (`{{`/`}}`) since these are plain `str.format()`
templates - a single unescaped brace is interpreted as a format field
and raises `KeyError` at prompt-build time. This is exactly the bug
that was found and fixed in graph_extraction_service.py's
EXTRACTION_PROMPT while building this module - the schema examples
below were written (and manually re-checked) with that fresh in mind.

Every `context` argument accepted here is expected to already be
citation_service.build_cited_context(...) output - this module never
formats sources itself.
"""

# ============================================================
# Analyze Documents
# ============================================================

ANALYZE_PROMPT_TEMPLATE = """You are an expert document analyst. Score and analyze the TARGET document against the criteria below.

Rules:
1. Base every finding ONLY on the source text below - never use outside knowledge or assume information not present.
2. Cite every claim inline using its source number in square brackets, e.g. "5 years of Python experience [1]". If the source only partially supports a claim, say so explicitly rather than inferring the rest.
3. Score relevance/fit from 0 (no match) to 100 (excellent match) against the criteria - be discriminating, not generous; most documents should NOT score above 80 unless they are a genuinely strong match.
4. List concrete findings that support the score, and separately list anything the criteria require that this document does NOT demonstrate ("missing_requirements") - return an empty array if there are none, never omit the key.
5. If reference document(s) appear among the numbered sources below, they are supporting context only (e.g. a job description, a policy) - never score them, only ever score the TARGET document, which is always the LAST numbered source.
6. Return ONLY valid JSON matching the schema below - no prose outside the JSON.

Criteria to evaluate against:
----------------
{criteria}
----------------

Source(s) - any reference document(s) first, followed by the TARGET document to score:
----------------
{context}
----------------

Schema:
{{
  "score": 0,
  "summary": "one-paragraph verdict, with [n] citations",
  "findings": [{{"point": "a specific supporting finding", "citation": 1}}],
  "missing_requirements": ["a criterion this document does not demonstrate", "..."]
}}
"""


def build_analyze_prompt(context: str, criteria: str = "") -> str:
    return ANALYZE_PROMPT_TEMPLATE.format(
        criteria=criteria or "General quality, completeness, and relevance.",
        context=context,
    )


ANALYZE_SYNTHESIS_PROMPT_TEMPLATE = """You are an expert document analyst. You have already scored {count} documents individually against the same criteria. Synthesize an overall ranking narrative from those results - do not re-derive scores.

Rules:
1. Base your narrative ONLY on the per-document results below - do not invent findings not already present in them.
2. Identify what separates the top-scoring documents from the rest.
3. Call out any requirement that MULTIPLE documents are missing - a pattern worth flagging across the whole set.
4. Return ONLY valid JSON matching the schema below - no prose outside the JSON.

Per-document results (already scored):
----------------
{results}
----------------

Schema:
{{
  "narrative": "an overall ranking summary across all documents",
  "common_gaps": ["a requirement several documents are missing", "..."]
}}
"""


def build_analyze_synthesis_prompt(results: str, count: int) -> str:
    return ANALYZE_SYNTHESIS_PROMPT_TEMPLATE.format(results=results, count=count)


# ============================================================
# Compare Documents
# ============================================================

COMPARE_PROMPT_TEMPLATE = """You are an expert comparative analyst. Compare the numbered documents below and identify their key similarities and differences.

Rules:
1. Base every comparison point ONLY on the source text below - never use outside knowledge.
2. Cite every claim inline using its source number in square brackets, e.g. "Document A requires 30 days notice [1], while Document B requires 60 [2]."
3. Organize differences by dimension (e.g. term length, price, obligations, scope) rather than restating each document in isolation.
4. For EACH document, also produce a short "position" - what is distinctive about that specific document relative to the others.
5. Return ONLY valid JSON matching the schema below - no prose outside the JSON.

Documents to compare:
----------------
{context}
----------------

Schema:
{{
  "overall_narrative": "a synthesized comparison across all documents, with [n] citations",
  "dimensions": [{{"dimension": "e.g. Term Length", "finding": "how documents differ, with [n] citations"}}],
  "per_document": [{{"document": "exact document title as given in the sources", "position": "what is distinctive about this one, with [n] citations"}}]
}}
"""


def build_compare_prompt(context: str) -> str:
    return COMPARE_PROMPT_TEMPLATE.format(context=context)


# ============================================================
# Summarize Documents
# ============================================================

SUMMARIZE_PROMPT_TEMPLATE = """You are an expert summarization engine. Summarize ONE document.

Rules:
1. Base the summary ONLY on the source text below - never use outside knowledge.
2. Cite every claim inline using its source number in square brackets, e.g. "Revenue grew 12% year over year [1]."
3. Target length: {length}.
4. Capture the document's main topic(s) and key findings/points, not a chronological restatement.
5. Return ONLY valid JSON matching the schema below - no prose outside the JSON.

Source:
----------------
{context}
----------------

Schema:
{{
  "summary": "the summary, with [n] citations",
  "key_points": ["a key point", "..."],
  "topics": ["a topic this document covers", "..."]
}}
"""


def build_summarize_prompt(context: str, length: str = "3-5 sentences") -> str:
    return SUMMARIZE_PROMPT_TEMPLATE.format(context=context, length=length)


EXECUTIVE_SUMMARY_PROMPT_TEMPLATE = """You are an expert summarization engine. You have already summarized {count} documents individually. Synthesize one executive summary across all of them - do not re-summarize each document from scratch.

Rules:
1. Base the executive summary ONLY on the per-document summaries below.
2. Identify common topics/themes across documents, and group similar documents together where relevant.
3. Highlight the most significant findings across the whole set, not just each document's own top point.
4. Return ONLY valid JSON matching the schema below - no prose outside the JSON.

Per-document summaries:
----------------
{summaries}
----------------

Schema:
{{
  "executive_summary": "a synthesized summary across all documents",
  "common_topics": ["a topic shared across multiple documents", "..."]
}}
"""


def build_executive_summary_prompt(summaries: str, count: int) -> str:
    return EXECUTIVE_SUMMARY_PROMPT_TEMPLATE.format(summaries=summaries, count=count)


# ============================================================
# Extract Information
# ============================================================

EXTRACT_PROMPT_TEMPLATE = """You are an expert information-extraction engine. Extract the requested fields from the source document below.

Rules:
1. Extract ONLY values explicitly present in the source text - never infer, guess, or fill in a plausible-sounding value.
2. If a requested field is not present in the source, set its value to null - do not omit the key and do not invent a value.
3. Cite every extracted value's source using its bracketed source number, e.g. {{"value": "March 2024", "citation": 1}}.
4. If no field list is given below, infer the 5-10 most salient fields this type of document would reasonably contain and extract those instead.
5. Return ONLY valid JSON matching the schema below - no prose outside the JSON.

Fields to extract:
----------------
{fields}
----------------

Source:
----------------
{context}
----------------

Schema:
{{"fields": {{"<field name>": {{"value": "<extracted value or null>", "citation": 1}}}}}}
"""


def build_extract_prompt(context: str, fields: list = None) -> str:
    return EXTRACT_PROMPT_TEMPLATE.format(
        fields=", ".join(fields) if fields else "(none specified - infer the most salient fields)",
        context=context,
    )


# ============================================================
# Validate Against Reference Documents
# ============================================================

VALIDATE_PROMPT_TEMPLATE = """You are an expert compliance analyst. Check ONE target document against the reference document(s) below (a policy, standard, or requirement set) and identify compliance and violations.

Rules:
1. Base every finding ONLY on the source text below - never use outside knowledge of what the reference "should" say.
2. Cite every claim inline using its source number in square brackets - reference sources and the target document are both numbered in the same source list.
3. Score compliance from 0 (does not comply at all) to 100 (fully compliant).
4. List concrete violations (where the target contradicts or fails to meet the reference) and separately list concrete compliant points (where the target explicitly meets the reference) - return empty arrays if there are none, never omit the keys.
5. Return ONLY valid JSON matching the schema below - no prose outside the JSON.

Reference document(s) and target document (numbered):
----------------
{context}
----------------

Schema:
{{
  "compliance_score": 0,
  "summary": "one-paragraph verdict, with [n] citations",
  "violations": [{{"issue": "a specific violation", "citation": 1, "severity": "high"}}],
  "compliant_points": [{{"point": "a specific point of compliance", "citation": 1}}]
}}

severity must be one of: "high", "medium", "low".
"""


def build_validate_prompt(context: str) -> str:
    return VALIDATE_PROMPT_TEMPLATE.format(context=context)


# ============================================================
# Find Similar Documents / Organize Documents
# (embedding-based clustering does the heavy lifting - see
# ai_tasks_similarity_service.py; the LLM is only used to label an
# already-computed cluster/group, never to compute similarity itself)
# ============================================================

CLUSTER_LABEL_PROMPT_TEMPLATE = """You are an expert content analyst. The documents below have been grouped together because they are similar. Give this group a short, descriptive label and explain what they have in common.

Rules:
1. Base the label and explanation ONLY on the excerpts below.
2. Keep the label short (2-6 words) - it will be shown as a group heading.
3. Return ONLY valid JSON matching the schema below - no prose outside the JSON.

Excerpts from documents in this group:
----------------
{excerpts}
----------------

Schema:
{{"label": "a short group label", "explanation": "one or two sentences on what these documents have in common"}}
"""


def build_cluster_label_prompt(excerpts: str) -> str:
    return CLUSTER_LABEL_PROMPT_TEMPLATE.format(excerpts=excerpts)


# ============================================================
# Generate Reports
# ============================================================

REPORT_EXTRACT_PROMPT_TEMPLATE = """You are an expert report writer. Extract the content from ONE source document that is relevant to the report focus below - this is raw material for a later synthesis step, not the final report.

Rules:
1. Extract ONLY content explicitly present in the source text - never use outside knowledge.
2. Cite every extracted point inline using its source number in square brackets.
3. Focus only on content relevant to the report's focus - ignore unrelated parts of the document.
4. Return ONLY valid JSON matching the schema below - no prose outside the JSON.

Report focus:
----------------
{focus}
----------------

Source:
----------------
{context}
----------------

Schema:
{{"relevant_points": [{{"point": "a point relevant to the report focus", "citation": 1}}]}}
"""


def build_report_extract_prompt(context: str, focus: str = "") -> str:
    return REPORT_EXTRACT_PROMPT_TEMPLATE.format(
        focus=focus or "A general overview of the document's content.",
        context=context,
    )


REPORT_SYNTHESIS_PROMPT_TEMPLATE = """You are an expert report writer. Synthesize a final report titled "{title}" from the extracted points below (already pulled from {count} source documents) - do not re-read the original documents, work only from these extracts.

Rules:
1. Base every section ONLY on the extracted points below.
2. Cite every claim inline using its source number in square brackets.
3. Organize the report into clear sections appropriate to the focus and the material available - do not force a fixed structure if the material doesn't support it.
4. Return ONLY valid JSON matching the schema below - no prose outside the JSON.

Report focus:
----------------
{focus}
----------------

Extracted points (numbered by source document):
----------------
{extracts}
----------------

Schema:
{{
  "title": "{title}",
  "executive_summary": "a short overview of the whole report, with [n] citations",
  "sections": [{{"heading": "a section heading", "body": "the section's content, with [n] citations"}}]
}}
"""


def build_report_synthesis_prompt(extracts: str, count: int, title: str = "Generated Report", focus: str = "") -> str:
    return REPORT_SYNTHESIS_PROMPT_TEMPLATE.format(
        extracts=extracts,
        count=count,
        title=title,
        focus=focus or "A general overview of the source documents.",
    )
