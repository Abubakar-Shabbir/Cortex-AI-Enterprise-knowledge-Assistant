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

    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
        help_text="Set by upload_service.process_uploaded_document() - "
                   "PENDING until the Embed button is clicked (documents_view.document_embed).",
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


# ============================================================
# RBAC
# ============================================================
#
# Role/Permission/UserRole are the single source of truth for
# authorization from here on - see RAG/services/permission_service.py
# for the read API and RAG/decorators.py / RAG/middleware.py for how
# views enforce it. is_staff/is_superuser are only ever read once, as
# the seed data source for existing accounts in
# RAG/management/commands/seed_rbac.py; no other code should branch on
# them going forward.

class Permission(models.Model):
    """
    A single grantable capability, namespaced as "<area>.<action>"
    (e.g. "users.suspend") so new areas can be added without colliding
    with existing codenames.
    """

    codename = models.CharField(
        max_length=100,
        unique=True
    )

    name = models.CharField(
        max_length=150
    )

    description = models.CharField(
        max_length=255,
        blank=True
    )

    class Meta:
        ordering = ["codename"]

    def __str__(self):
        return self.codename

    @property
    def namespace(self):
        """The "<area>" half of "<area>.<action>" - lets the Role Management UI group permissions by area without a second lookup table."""
        return self.codename.split(".")[0]


class Role(models.Model):
    """
    A named bundle of Permissions. Adding a future role (Manager, HR,
    Auditor, ...) means creating a Role row and attaching Permissions
    to it - no code changes required, since every permission check
    goes through Role.has_permission() / permission_service, never a
    hardcoded role name.
    """

    name = models.CharField(
        max_length=100,
        unique=True
    )

    slug = models.SlugField(
        max_length=100,
        unique=True
    )

    description = models.CharField(
        max_length=255,
        blank=True
    )

    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="roles"
    )

    is_system = models.BooleanField(
        default=False,
        help_text="Built-in role (super_admin/admin/user) seeded by seed_rbac - not meant to be deleted.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def has_permission(self, codename):
        return self.permissions.filter(codename=codename).exists()


class UserRole(models.Model):
    """
    A user's single active role. One-to-one rather than many-to-many:
    this product's roles (Super Admin / Admin / User, and whatever is
    added later) are mutually exclusive tiers, not stackable grants -
    a user needing broader access gets reassigned, not given a second
    role.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="role_assignment"
    )

    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="user_assignments"
    )

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+"
    )

    assigned_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.user} -> {self.role}"


class ActivityLog(models.Model):
    """
    A workspace-wide audit trail entry, written by
    RAG.services.activity_log_service.log_activity() for events that
    aren't already captured by an existing model (Document.uploaded_at
    already records uploads; this covers deletions, suspensions, role
    changes, and logins). Backs Admin > Activity Logs
    (RAG.views.admin_activity_logs_view).
    """

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs"
    )

    action = models.CharField(
        max_length=50,
        db_index=True,
        help_text='Namespaced event, e.g. "document.deleted", "user.suspended".',
    )

    description = models.CharField(
        max_length=255
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action}: {self.description}"


class SystemConfiguration(models.Model):
    """
    Singleton row (always pk=1) holding the live-editable subset of RAG
    pipeline configuration - see RAG/services/system_config_service.py,
    which is the only code that should read/write this model directly.
    Everything here is applied on top of settings.py at runtime
    (apply_config_to_settings()), so every existing consumer of
    settings.TOP_K / settings.ENABLE_HYDE / etc. keeps working
    unchanged - this model never replaces settings.py, it overrides it.

    Deliberately NOT included: embedding model (changing it needs a
    migration + re-embedding every existing chunk, not a config flip),
    database connection (editing it live is operationally circular -
    you'd be writing the new value through the connection you're about
    to replace), and raw API keys (secrets belong in environment
    variables, not a database row editable from a browser).
    """

    LLM_PROVIDER_CHOICES = [
        ("gemini", "Gemini"),
        ("openrouter", "OpenRouter"),
    ]

    llm_provider = models.CharField(max_length=20, choices=LLM_PROVIDER_CHOICES, default="openrouter")

    top_k = models.PositiveSmallIntegerField(default=3)
    answer_temperature = models.FloatField(default=0.2)

    chunk_size = models.PositiveIntegerField(
        default=800,
        help_text="Applies to newly-uploaded documents only - existing chunks aren't retroactively resized.",
    )
    chunk_overlap = models.PositiveIntegerField(default=150)

    enable_query_expansion = models.BooleanField(default=False)
    enable_hyde = models.BooleanField(default=False)
    enable_multi_query = models.BooleanField(default=False)
    multi_query_variants = models.PositiveSmallIntegerField(default=3)

    enable_dynamic_top_k = models.BooleanField(default=True)
    dynamic_top_k_max = models.PositiveSmallIntegerField(default=10)

    enable_reranker = models.BooleanField(default=False)
    reranker_candidate_multiplier = models.PositiveSmallIntegerField(default=3)

    enable_context_compression = models.BooleanField(default=False)
    context_compression_threshold = models.FloatField(default=0.92)

    updated_at = models.DateTimeField(auto_now=True)

    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+"
    )

    class Meta:
        verbose_name = "System Configuration"

    def __str__(self):
        return "System Configuration"
