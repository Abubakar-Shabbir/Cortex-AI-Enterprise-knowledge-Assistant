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
