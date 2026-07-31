from django.contrib import admin

from .models import ChunkEmbedding, Document, DocumentChunk, QueryLog


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "file_type", "chunk_count", "file_size", "uploaded_at")
    list_filter = ("file_type",)
    search_fields = ("title", "user__username")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_number", "created_at")
    list_filter = ("document",)


@admin.register(ChunkEmbedding)
class ChunkEmbeddingAdmin(admin.ModelAdmin):
    list_display = ("chunk", "embedding_model", "created_at")
    list_filter = ("embedding_model",)


@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "confidence", "response_time_ms", "created_at")
    list_filter = ("user", "search_method")
    search_fields = ("question", "answer")
