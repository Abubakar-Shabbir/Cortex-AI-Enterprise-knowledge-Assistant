from django.contrib.auth.models import User
from django.db import models
from pgvector.django import VectorField
from django.conf import settings

class Document(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    title = models.CharField(
        max_length=200
    )

    file = models.FileField(
        upload_to="documents/"
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    file_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True
    )
    file_size = models.BigIntegerField(
        default=0
    )

    file_type = models.CharField(
        max_length=20,
        blank=True
    )

    chunk_count = models.PositiveIntegerField(
        default=0
    )

    def __str__(self):
        return self.title


class DocumentChunk(models.Model):

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks"
    )

    content = models.TextField()

    chunk_number = models.PositiveIntegerField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["chunk_number"]

    def __str__(self):
        return f"{self.document.title} - Chunk {self.chunk_number}"


class ChunkEmbedding(models.Model):

    chunk = models.OneToOneField(
        DocumentChunk,
        on_delete=models.CASCADE,
        related_name="vector"
    )

    embedding = VectorField(
        dimensions=settings.EMBEDDING_DIMENSION
    )

    embedding_model = models.CharField(
        max_length=100,
        default="all-MiniLM-L6-v2"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return (
            f"{self.chunk.document.title} "
            f"- Embedding ({self.embedding_model})"
        )


class QueryLog(models.Model):
    """
    Records every question asked so the
    Search History and Analytics pages can
    show real usage instead of placeholders.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="query_logs"
    )

    question = models.TextField()

    answer = models.TextField()

    sources = models.JSONField(
        default=list,
        blank=True
    )

    search_method = models.CharField(
        max_length=50,
        default="Hybrid (Vector + BM25)"
    )

    response_time_ms = models.PositiveIntegerField(
        default=0
    )

    confidence = models.PositiveSmallIntegerField(
        default=0
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username}: {self.question[:50]}"


class Entity(models.Model):
    """
    A normalized, deduplicated entity mentioned in one or more of
    the user's document chunks. Entity types are a free-form string
    rather than a fixed choices list so new types (from the LLM
    extractor or future extractors) don't require a migration.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="entities"
    )

    name = models.CharField(
        max_length=255,
        db_index=True
    )

    display_name = models.CharField(
        max_length=255
    )

    entity_type = models.CharField(
        max_length=50,
        db_index=True,
        default="MISC"
    )

    mention_count = models.PositiveIntegerField(
        default=0
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["name"]
        unique_together = ("user", "name", "entity_type")

    def __str__(self):
        return f"{self.display_name} ({self.entity_type})"


class EntityMention(models.Model):
    """
    Links an Entity to the DocumentChunk it was extracted from, so
    graph retrieval can pull the supporting chunk content for a
    matched entity.
    """

    entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="mentions"
    )

    chunk = models.ForeignKey(
        DocumentChunk,
        on_delete=models.CASCADE,
        related_name="entity_mentions"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        unique_together = ("entity", "chunk")

    def __str__(self):
        return f"{self.entity.display_name} in {self.chunk}"


class Relationship(models.Model):
    """
    A directed, deduplicated edge between two entities. Re-extracting
    the same (source, relation, target) triple from another chunk
    increments weight instead of creating a duplicate row.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="relationships"
    )

    source = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="outgoing_relationships"
    )

    target = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="incoming_relationships"
    )

    relation_type = models.CharField(
        max_length=100,
        db_index=True
    )

    context = models.TextField(
        blank=True,
        default=""
    )

    weight = models.PositiveIntegerField(
        default=1
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-weight"]
        unique_together = ("user", "source", "target", "relation_type")

    def __str__(self):
        return f"{self.source.display_name} -[{self.relation_type}]-> {self.target.display_name}"
