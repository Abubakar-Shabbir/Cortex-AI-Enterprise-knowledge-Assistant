"""
CSV report export (Reports page).

Uses the stdlib `csv` module writing straight into the HttpResponse
the view returns - no new dependency, no intermediate file on disk.
Each function here only builds the *rows*; the view is responsible
for the HttpResponse/csv.writer plumbing, so these stay easy to unit
test without touching the request/response cycle.
"""

from ..models import AITaskRun, Document, QueryLog

DOCUMENTS_REPORT_HEADER = [
    "Title", "File Type", "File Size (bytes)", "Chunk Count", "Uploaded At",
]

AI_TASK_RUNS_REPORT_HEADER = [
    "Task Type", "Status", "Documents", "Error", "Started At", "Completed At", "Created At",
]

KNOWLEDGE_TOPICS_REPORT_HEADER = [
    "Topic", "Category", "Mentions", "Connected Documents", "Contributors",
]

USAGE_REPORT_HEADER = [
    "Question", "Answer", "Search Method", "Confidence (%)", "Response Time (ms)", "Asked At",
]

COMPARISON_REPORT_HEADER = [
    "Metric", "Current Period", "Previous Period", "Change (%)",
]

AI_TASK_RESULTS_HEADER = [
    "Rank", "Document", "Score", "Title", "Summary", "Citations",
]


def get_documents_report_rows(user):
    """
    One row per document owned by `user`, most recently uploaded
    first.
    """

    documents = Document.objects.filter(user=user).order_by("-uploaded_at")

    return [
        [
            document.title,
            document.file_type,
            document.file_size,
            document.chunk_count,
            document.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
        ]
        for document in documents
    ]


def get_usage_report_rows(user):
    """
    One row per question `user` has asked, most recent first.
    """

    logs = QueryLog.objects.filter(user=user).order_by("-created_at")

    return [
        [
            log.question,
            log.answer,
            log.search_method,
            log.confidence,
            log.response_time_ms,
            log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ]
        for log in logs
    ]


QUERIES_REPORT_HEADER_METADATA = [
    "Owner", "Status", "Search Method", "Confidence (%)", "Response Time (ms)", "Sources", "Flagged", "Asked At",
]

QUERIES_REPORT_HEADER_WITH_CONTENT = [
    "Owner", "Question", "Answer", "Status", "Search Method", "Confidence (%)", "Response Time (ms)", "Sources", "Flagged", "Asked At",
]


def get_queries_report_rows(logs, include_content):
    """
    One row per QueryLog in `logs` (already filtered/sorted by the
    caller - see queries_service.filter_and_sort_queries), for the
    Admin > Queries CSV export. `include_content` gates whether
    Question/Answer columns are present at all - the caller is
    responsible for only passing True when the actor holds
    "queries.view_content" (see RAG.views.export_queries_report),
    same privacy boundary as the on-page table.
    """

    from .prompt_templates import is_not_found_answer

    rows = []

    for log in logs:
        status = "No Answer Found" if is_not_found_answer(log.answer) else "Answered"
        common = [
            log.user.username,
        ]
        if include_content:
            common += [log.question, log.answer]
        common += [
            status,
            log.search_method,
            log.confidence,
            log.response_time_ms,
            len(log.sources or []),
            "Yes" if log.is_flagged else "No",
            log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ]
        rows.append(common)

    return rows


def get_comparison_report_rows(comparison_data):
    """
    One row per metric in `comparison_data["rows"]` (see
    stats_service.get_comparison_report_data) - the CSV counterpart to
    the on-page Comparative Report table on the Reports page.
    """

    return [
        [row["label"], row["current"], row["previous"], row["change_pct"]]
        for row in comparison_data["rows"]
    ]


def get_ai_task_result_rows(run):
    """
    One row per AITaskResult belonging to `run`, in its own display
    order (see AITaskResult.Meta.ordering). Generic across all 8 task
    types - reads only the common fields (rank/document/score/title/
    summary/citations), never task-specific `data` keys, since the
    on-page results table is where the rich, per-type rendering lives;
    this CSV is the flat, universal export.
    """

    rows = []

    for result in run.results.select_related("document").all():
        document_label = result.document.title if result.document_id else (result.title or "(overall)")
        citations_label = ", ".join(f"[{c['number']}] {c['document']}" for c in (result.citations or []))

        rows.append([
            result.rank if result.rank is not None else "",
            document_label,
            result.score if result.score is not None else "",
            result.title,
            result.summary,
            citations_label,
        ])

    return rows


def get_ai_task_runs_report_rows(user):
    """
    One row per AITaskRun `user` has ever started, most recent first -
    the AI Tasks counterpart to the Usage Report, but at the run level
    rather than the per-result level get_ai_task_result_rows()/
    ai_task_export already covers for a single run.
    """

    runs = AITaskRun.objects.filter(user=user).order_by("-created_at")

    return [
        [
            run.get_task_type_display(),
            run.get_status_display(),
            run.document_count,
            run.error_message,
            run.started_at.strftime("%Y-%m-%d %H:%M:%S") if run.started_at else "",
            run.completed_at.strftime("%Y-%m-%d %H:%M:%S") if run.completed_at else "",
            run.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ]
        for run in runs
    ]


def get_knowledge_topics_report_rows(user):
    """
    One row per Topic visible to `user` (see
    knowledge_service.list_all_topics - the same accessible-scoped,
    cross-uploader-merged Topic list Explore Topics itself uses), most
    mentioned first.
    """

    from .knowledge_service import list_all_topics

    return [
        [
            topic["display_name"],
            topic["entity_type"],
            topic["mention_count"],
            topic["document_count"],
            topic["member_count"],
        ]
        for topic in list_all_topics(user)
    ]
