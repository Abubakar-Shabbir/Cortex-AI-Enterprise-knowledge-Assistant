"""
Metadata filtering for retrieval.

RetrievalFilters is a small, explicit set of document-level filters
that vector_search(), hyde_search(), bm25_search(), and graph_search()
all accept and apply the same way (apply_document_filters()), so a
caller can narrow retrieval to specific documents, file types, an
upload date range, a Collection, a Category/Tag, or Organization
Library membership, without each retrieval source reimplementing the
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
    collection_id: Optional[int] = None
    category_id: Optional[int] = None
    tag_id: Optional[int] = None
    org_library_only: bool = False

    def is_empty(self) -> bool:
        return not any((
            self.document_ids,
            self.file_types,
            self.uploaded_after,
            self.uploaded_before,
            self.collection_id,
            self.category_id,
            self.tag_id,
            self.org_library_only,
        ))

    @classmethod
    def from_request(
        cls,
        document_ids=None,
        file_types=None,
        uploaded_after=None,
        uploaded_before=None,
        collection_id=None,
        category_id=None,
        tag_id=None,
        org_library_only=False,
    ) -> "RetrievalFilters":
        """
        Build filters from loosely-typed request input, e.g. POSTed
        document_id values from the Select Documents dialog
        (request.POST.getlist("document_ids")) or a single Collection/
        Category/Tag id string from a <select>. Invalid or empty input
        for a field simply leaves that field unset rather than raising
        - filtering is a refinement, not a hard precondition, so bad
        input degrades to "no filter" instead of a 500.
        """

        normalized_document_ids = None

        if document_ids:
            parsed = []
            for value in document_ids:
                try:
                    parsed.append(int(value))
                except (TypeError, ValueError):
                    continue
            normalized_document_ids = tuple(parsed) or None

        normalized_file_types = None

        if file_types:
            normalized_file_types = tuple(
                file_type.strip().lower()
                for file_type in file_types
                if file_type and file_type.strip()
            ) or None

        def _parse_id(value):
            if value in (None, ""):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        return cls(
            document_ids=normalized_document_ids,
            file_types=normalized_file_types,
            uploaded_after=uploaded_after,
            uploaded_before=uploaded_before,
            collection_id=_parse_id(collection_id),
            category_id=_parse_id(category_id),
            tag_id=_parse_id(tag_id),
            org_library_only=bool(org_library_only),
        )


def apply_document_filters(queryset, filters: Optional[RetrievalFilters], *, document_field: str):
    """
    Apply a RetrievalFilters to a queryset that reaches Document via
    `document_field` - e.g. "chunk__document" for a ChunkEmbedding or
    EntityMention queryset, "document" for a DocumentChunk queryset.

    No-op (returns the queryset unchanged) if filters is None or empty,
    so every retrieval function stays behaviorally identical when the
    caller doesn't pass filters at all. Every lookup here narrows a
    queryset that's already been scoped to the requester's accessible
    document set upstream (see document_access_service) - this is a
    refinement on top of that boundary, never a way around it.
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

    if filters.collection_id:
        lookups[f"{document_field}__collections__id"] = filters.collection_id

    if filters.category_id:
        lookups[f"{document_field}__category_id"] = filters.category_id

    if filters.tag_id:
        lookups[f"{document_field}__tags__id"] = filters.tag_id

    if filters.org_library_only:
        lookups[f"{document_field}__is_org_library"] = True

    return queryset.filter(**lookups)
