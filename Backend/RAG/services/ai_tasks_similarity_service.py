"""
Document-level embedding and clustering for Find Similar Documents /
Organize Documents.

Deliberately reuses the ChunkEmbedding rows already computed at upload
time (RAG.services.embedding_service / vector_service) rather than
re-embedding anything - a document's "document-level" embedding is
just the mean of its own chunks' embeddings. Similarity/clustering is
pure numpy over an N-by-N matrix (N capped at
settings.AI_TASKS_MAX_DOCUMENTS, so this is always small - 100x100 is
trivial), never an O(N^2) LLM or DB call.
"""

import logging

import numpy as np

from ..models import ChunkEmbedding

logger = logging.getLogger(__name__)

DEFAULT_SIMILARITY_THRESHOLD = 0.85


def build_document_embedding(document):
    """
    Mean-pools every ChunkEmbedding row belonging to `document`'s
    chunks into one vector. Returns None (not an exception) if the
    document has no embeddings yet - i.e. it hasn't been through
    "Embed" (processing_status != COMPLETED) - so the caller can
    exclude it from clustering rather than crash the run.
    """

    vectors = list(
        ChunkEmbedding.objects.filter(chunk__document=document).values_list("embedding", flat=True)
    )

    if not vectors:
        return None

    matrix = np.array(vectors, dtype=float)

    return matrix.mean(axis=0)


def cosine_similarity_matrix(embeddings: list) -> np.ndarray:
    """
    `embeddings` is a list of 1D numpy vectors (same dimension, no
    Nones - callers filter those out first). Returns an N-by-N cosine
    similarity matrix, values in [-1, 1] (typically [0, 1] for
    non-negative embedding spaces).
    """

    matrix = np.vstack(embeddings)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9  # avoid division by zero for a degenerate all-zero embedding
    normalized = matrix / norms

    return normalized @ normalized.T


def cluster_documents(document_ids: list, embeddings: list, threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
    """
    Threshold-based connected-components clustering (plain Python
    union-find) over the cosine similarity matrix - groups documents
    that are all pairwise-similar (directly or transitively through
    another similar document) above `threshold`.

    `document_ids`/`embeddings` must be parallel lists (same order,
    same length, no None embeddings - filter those out first, see
    build_document_embedding's None contract).

    Returns a list of clusters, each
    {"document_ids": [...], "centroid": <1D numpy vector>} - singleton
    "clusters" (documents with no similar match above threshold) are
    NOT included, since a cluster of one is not a match worth
    reporting for Find Similar/Organize's default grouping.
    """

    n = len(document_ids)

    if n < 2:
        return []

    similarity = cosine_similarity_matrix(embeddings)

    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    for i in range(n):
        for j in range(i + 1, n):
            if similarity[i, j] >= threshold:
                union(i, j)

    groups = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    clusters = []
    for indices in groups.values():
        if len(indices) < 2:
            continue
        member_ids = [document_ids[i] for i in indices]
        centroid = np.mean([embeddings[i] for i in indices], axis=0)
        clusters.append({"document_ids": member_ids, "centroid": centroid})

    return clusters


def split_into_groups(document_ids: list, embeddings: list, target_groups: int):
    """
    Greedy split for Organize Documents when the user specifies a
    target group count, instead of a similarity threshold. Not a real
    k-means (no scikit-learn dependency in this project) - a simple,
    deterministic greedy assignment: pick the target_groups documents
    that are most mutually dissimilar as seeds, then assign every
    other document to whichever seed it's most similar to. Good
    enough for "organize N documents into roughly K groups" without a
    new ML dependency; not claimed to be optimal clustering.

    Returns a list of {"document_ids": [...], "centroid": ...} - one
    per group, every input document assigned to exactly one (no
    "unclustered" documents, unlike cluster_documents()).
    """

    n = len(document_ids)
    target_groups = max(1, min(target_groups, n))

    if target_groups >= n:
        return [
            {"document_ids": [document_ids[i]], "centroid": embeddings[i]}
            for i in range(n)
        ]

    similarity = cosine_similarity_matrix(embeddings)

    # Seed selection: start from document 0, then repeatedly pick the
    # document least similar to every seed chosen so far - a cheap
    # farthest-point heuristic for spreading seeds across the set.
    seeds = [0]
    while len(seeds) < target_groups:
        remaining = [i for i in range(n) if i not in seeds]
        next_seed = min(remaining, key=lambda i: max(similarity[i, s] for s in seeds))
        seeds.append(next_seed)

    assignments = {seed_index: [seed_index] for seed_index in seeds}

    for i in range(n):
        if i in seeds:
            continue
        best_seed = max(seeds, key=lambda s: similarity[i, s])
        assignments[best_seed].append(i)

    groups = []
    for indices in assignments.values():
        member_ids = [document_ids[i] for i in indices]
        centroid = np.mean([embeddings[i] for i in indices], axis=0)
        groups.append({"document_ids": member_ids, "centroid": centroid})

    return groups


def similarity_to_centroid(embedding, centroid) -> float:
    """Cosine similarity between one document's embedding and its cluster/group centroid - used as AITaskResult.score for per-document rows."""

    norm_a = np.linalg.norm(embedding)
    norm_b = np.linalg.norm(centroid)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(embedding, centroid) / (norm_a * norm_b))
