"""
My Documents - filtering/sorting and status-label computation for the
enhanced Documents list. Mirrors queries_service.py's param-dict
filter/sort pattern and annotate_status() convention from the same
project.
"""

from django.utils.text import slugify

from ..utils.formatting import format_bytes

SORT_OPTIONS = {
    "newest": "-uploaded_at",
    "oldest": "uploaded_at",
    "title": "title",
    "size_desc": "-file_size",
    "size_asc": "file_size",
}

DEFAULT_SORT = "newest"


def filter_and_sort_documents(base_queryset, params):
    """
    Apply search/status/type/category/tag/date/archived filters and
    sorting to `base_queryset` (already scoped by the caller - owned,
    accessible, org-library, whatever the page needs). Archived
    documents are excluded by default unless `archived=1` (archived
    only) or `archived=all` (both) is explicitly requested, matching
    the common "archived is hidden unless asked for" convention.
    """

    documents = base_queryset

    search_query = params.get("q", "").strip()
    if search_query:
        documents = documents.filter(title__icontains=search_query)

    file_type = params.get("file_type", "").strip()
    if file_type:
        documents = documents.filter(file_type__iexact=file_type)

    category_id = params.get("category", "").strip()
    if category_id.isdigit():
        documents = documents.filter(category_id=int(category_id))

    tag_id = params.get("tag", "").strip()
    if tag_id.isdigit():
        documents = documents.filter(tags__id=int(tag_id))

    status = params.get("status", "").strip()
    if status in ("pending", "processing", "completed", "failed"):
        documents = documents.filter(processing_status=status)

    date_from = params.get("date_from", "").strip()
    if date_from:
        documents = documents.filter(uploaded_at__date__gte=date_from)

    date_to = params.get("date_to", "").strip()
    if date_to:
        documents = documents.filter(uploaded_at__date__lte=date_to)

    archived = params.get("archived", "").strip()
    if archived == "1":
        documents = documents.filter(is_archived=True)
    elif archived != "all":
        documents = documents.filter(is_archived=False)

    sort = params.get("sort", DEFAULT_SORT)
    documents = documents.order_by(SORT_OPTIONS.get(sort, SORT_OPTIONS[DEFAULT_SORT]))

    return documents.distinct()


def annotate_document_status(documents):
    """
    Attach a status/percent/formatted-size dict per Document in
    `documents` (a list, not a queryset - call after slicing/
    pagination, and after annotating each with `.embedded_chunks`).
    "Ready" is the current label for a fully-embedded document
    (documents_view previously called this "Embedded" - the Enterprise
    Document Center rename standardizes on "Ready"); "Archived"
    overrides whatever the underlying processing status is, since an
    archived document's processing history still matters (kept in
    `percent`) but its actionable status to the viewer is just that
    it's archived.
    """

    result = []

    for doc in documents:
        embedded = getattr(doc, "embedded_chunks", 0)

        if doc.processing_status == doc.ProcessingStatus.PENDING:
            base_status, percent = "Pending", 0
        elif doc.processing_status == doc.ProcessingStatus.FAILED:
            base_status, percent = "Failed", 0
        elif doc.processing_status == doc.ProcessingStatus.PROCESSING:
            base_status = "Processing"
            percent = round((embedded / doc.chunk_count) * 100) if doc.chunk_count else 0
        elif doc.chunk_count and embedded >= doc.chunk_count:
            base_status, percent = "Ready", 100
        else:
            base_status = "Partial"
            percent = round((embedded / doc.chunk_count) * 100) if doc.chunk_count else 0

        status = "Archived" if doc.is_archived else base_status

        result.append({
            "doc": doc,
            "status": status,
            "percent": percent,
            "file_size": format_bytes(doc.file_size),
        })

    return result


def unique_slug(model_cls, user, name):
    """Shared slugify-with-suffix helper for Tag/Category creation - both are unique_together(user, slug)."""

    base = slugify(name)[:50] or "item"
    slug = base
    suffix = 2

    while model_cls.objects.filter(user=user, slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1

    return slug
