"""
CSV report export (Reports page).

Uses the stdlib `csv` module writing straight into the HttpResponse
the view returns - no new dependency, no intermediate file on disk.
Each function here only builds the *rows*; the view is responsible
for the HttpResponse/csv.writer plumbing, so these stay easy to unit
test without touching the request/response cycle.
"""

from ..models import Document, QueryLog

DOCUMENTS_REPORT_HEADER = [
    "Title", "File Type", "File Size (bytes)", "Chunk Count", "Uploaded At",
]

USAGE_REPORT_HEADER = [
    "Question", "Answer", "Search Method", "Confidence (%)", "Response Time (ms)", "Asked At",
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
