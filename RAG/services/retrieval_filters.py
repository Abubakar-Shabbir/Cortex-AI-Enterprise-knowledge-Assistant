"""
Metadata filtering for retrieval.

RetrievalFilters is a small, explicit set of document-level filters
that vector_search(), hyde_search(), bm25_search(), and graph_search()
all accept and apply the same way (apply_document_filters()), so a
caller can narrow retrieval to specific documents, file types, or an
upload date range without each retrieval source reimplementing the
filtering logic.

Filters are entirely opt-in: the default `filters=None` on every
retrieval function preserves the exact prior, unfiltered behavior.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class RetrievalFilters:
    document_ids: Optional[tuple] = None
    file_types: Optional[tuple] = None
    uploaded_after: Optional[date] = None
    uploaded_before: Optional[date] = None

    def is_empty(self) -> bool:
        return not any((
            self.document_ids,
            self.file_types,
            self.uploaded_after,
            self.uploaded_before,
        ))

    @classmethod
    def from_request(
        cls,
        document_id=None,
        file_types=None,
        uploaded_after=None,
        uploaded_before=None,
    ) -> "RetrievalFilters":
        """
        Build filters from loosely-typed request input, e.g. a single
        POSTed document_id string from an HTML <select>. Invalid or
        empty input for a field simply leaves that field unset rather
        than raising - filtering is a refinement, not a hard
        precondition, so bad input degrades to "no filter" instead of
        a 500.
        """

        document_ids = None

        if document_id not in (None, ""):
            try:
                document_ids = (int(document_id),)
            except (TypeError, ValueError):
                document_ids = None

        normalized_file_types = None

        if file_types:
            normalized_file_types = tuple(
                file_type.strip().lower()
                for file_type in file_types
                if file_type and file_type.strip()
            ) or None

        return cls(
            document_ids=document_ids,
            file_types=normalized_file_types,
            uploaded_after=uploaded_after,
            uploaded_before=uploaded_before,
        )


def apply_document_filters(queryset, filters: Optional[RetrievalFilters], *, document_field: str):
    """
    Apply a RetrievalFilters to a queryset that reaches Document via
    `document_field` - e.g. "chunk__document" for a ChunkEmbedding or
    EntityMention queryset, "document" for a DocumentChunk queryset.

    No-op (returns the queryset unchanged) if filters is None or empty,
    so every retrieval function stays behaviorally identical when the
    caller doesn't pass filters at all.
    """

    if not filters or filters.is_empty():
        return queryset

    lookups = {}

    if filters.document_ids:
        lookups[f"{document_field}__id__in"] = filters.document_ids

    if filters.file_types:
        lookups[f"{document_field}__file_type__in"] = filters.file_types

    if filters.uploaded_after:
        lookups[f"{document_field}__uploaded_at__date__gte"] = filters.uploaded_after

    if filters.uploaded_before:
        lookups[f"{document_field}__uploaded_at__date__lte"] = filters.uploaded_before

    return queryset.filter(**lookups)
