from django.contrib.auth.models import User
from django.db import models
from pgvector.django import HnswIndex, VectorField
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

    description = models.TextField(blank=True, default="")

    is_org_library = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Admin-managed Organization Library membership - visible/retrievable "
                   "to every user, not just the owner. See document_access_service.",
    )

    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    category = models.ForeignKey(
        "Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )

    tags = models.ManyToManyField("Tag", blank=True, related_name="documents")

    version_number = models.PositiveIntegerField(
        default=1,
        help_text="Current version. Prior versions are snapshotted into DocumentVersion "
                   "by upload_service.upload_new_version() before this is incremented.",
    )

    processing_attempts = models.IntegerField(default=0)
    processing_error = models.TextField(blank=True, default="")
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class Category(models.Model):
    """A single-valued grouping, scoped per user - each user keeps their own category vocabulary, same as Tag, so categorizing a shared/org document never leaks a category name to its other viewers."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "slug")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Tag(models.Model):
    """A multi-valued label, scoped per user - see Category's docstring for why."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "slug")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Collection(models.Model):
    """A personal folder. The owner need not own every document inside it - only be able to access it (checked in collections_service, not a DB constraint), since filing an org/shared document into your own folder is a legitimate use case."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="collections")
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=255, blank=True, default="")
    documents = models.ManyToManyField(
        Document, through="CollectionDocument", related_name="collections"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class CollectionDocument(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name="items")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="collection_memberships")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("collection", "document")


class Favorite(models.Model):
    """Any accessible document can be favorited, not just an owned one - see document_access_service.can_view_document."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorite_documents")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "document")


class DocumentVersion(models.Model):
    """
    History-only snapshot of a document's PREVIOUS active file, written
    right before that file gets replaced (upload_service.upload_new_version).
    Document.file/.file_hash/.file_size/.file_type/.version_number always
    describe the CURRENT version; this table only ever grows - there is no
    "restore as current" action.
    """

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    file = models.FileField(upload_to="documents/versions/")
    file_hash = models.CharField(max_length=64, blank=True, default="")
    file_size = models.BigIntegerField(default=0)
    file_type = models.CharField(max_length=20, blank=True)
    replaced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("document", "version_number")
        ordering = ["-version_number"]


class DocumentShare(models.Model):
    """
    Exactly one of shared_with_user / shared_with_role / invited_email is
    set (enforced by the CheckConstraint below). Grants view + download
    only - never delete/re-version/manage-shares; those stay owner-only
    regardless of any share (see document_access_service.can_edit_document).

    invited_email is the pending state for "shared with someone who
    doesn't have an account yet" - it grants nothing by itself
    (document_access_service never looks at it), and is the ONLY field
    here that ever changes after creation: RAG.services.otp_service.
    verify_otp() converts it to a real shared_with_user the moment that
    exact email address is verified via OTP, which is also the moment
    ownership of the address is actually proven - see that function's
    own docstring for the full rationale.
    """

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="shares")
    shared_with_user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="document_shares_received"
    )
    shared_with_role = models.ForeignKey(
        "Role", on_delete=models.CASCADE, null=True, blank=True, related_name="document_shares"
    )
    invited_email = models.CharField(
        max_length=254, blank=True, default="",
        help_text="Set only while pending - an email with no matching account yet. Cleared (and shared_with_user set) once that address completes signup + OTP verification.",
    )
    shared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(shared_with_user__isnull=False, shared_with_role__isnull=True, invited_email="")
                    | models.Q(shared_with_user__isnull=True, shared_with_role__isnull=False, invited_email="")
                    | models.Q(shared_with_user__isnull=True, shared_with_role__isnull=True, invited_email__gt="")
                ),
                name="documentshare_exactly_one_target",
            ),
            # A plain unique_together on ("document", "invited_email")
            # would treat every non-invite row's blank "" the same as
            # any other row's blank "" - Postgres uniqueness doesn't
            # exempt empty string the way it exempts NULL, so two
            # ordinary user/role shares on the same document would
            # collide with each other. Scoped (partial) instead:
            # uniqueness only applies among rows that are actually a
            # pending invite (invited_email not blank).
            models.UniqueConstraint(
                fields=["document", "invited_email"],
                condition=models.Q(invited_email__gt=""),
                name="documentshare_unique_pending_invite",
            ),
        ]
        unique_together = [
            ("document", "shared_with_user"),
            ("document", "shared_with_role"),
        ]


class DocumentAccessLog(models.Model):
    """Powers Recent Documents - written on document_download/document_preview, not on every list-page render."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="document_accesses")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="access_logs")
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-accessed_at"])]


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

    class Meta:
        # HNSW, not IVFFlat: IVFFlat needs representative data present
        # at index-creation time to pick good cluster centroids and a
        # tuned `lists` parameter, and degrades badly on a small/empty
        # table; HNSW needs neither and searches correctly from the
        # first row. opclasses matches L2Distance - the only distance
        # function every retrieval query in this project actually
        # uses (retrieval_service._vector_similarity_search) - an
        # index built for a different operator wouldn't be used by
        # these queries at all.
        indexes = [
            HnswIndex(
                name="chunkembedding_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_l2_ops"],
            )
        ]

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

    structured_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Non-plain-text answer extras at the time this question was asked - "
                   "{'key_points': [...], 'table': {...} or None}. Persisted so replaying "
                   "a question from Search History (RAG.views.ask_ai's ?log_id= path) can "
                   "show the same structured findings the live answer did, instead of just "
                   "the answer text. A streamed answer (RAG.views.ask_ai_stream) always "
                   "writes {'key_points': [], 'table': None} here since it's plain text.",
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

    is_flagged = models.BooleanField(
        default=False,
        help_text="Pinned for follow-up in Admin > Queries. A shared review flag, not tied to any one admin.",
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
#
# There is no "Super Admin" tier - Admin is the sole built-in top-tier
# role and always has full access (see Role.has_permission below).
# Every other role (including the built-in "user") is fully dynamic:
# created, edited, and deleted through Admin > Roles
# (RAG.views.admin_roles_view), with permissions assigned per role,
# not hardcoded per feature.

ADMIN_ROLE_SLUG = "admin"
USER_ROLE_SLUG = "user"


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
        help_text="Built-in role (admin/user) seeded by seed_rbac - not meant to be deleted.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def has_permission(self, codename):
        # Admin always has full system access by design (not just at
        # seed time) - a permission added months from now still just
        # works for Admin without anyone remembering to attach it.
        # The M2M table is still kept in sync for Admin (see the
        # Permission post_save signal in RAG/apps.py and
        # RAG.admin.RoleAdmin.save_related) purely so the Role
        # Management UI's checkboxes show the truth, not because this
        # check depends on it.
        if self.slug == ADMIN_ROLE_SLUG:
            return True
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
    RAG.services.activity_log_service.log_activity() - either from a
    specific call site (document deleted, role changed, login, ...) or
    generically for every other request by
    RAG.middleware.RequestActivityMiddleware (action="page.<url_name>"),
    which only fires when nothing more specific already logged that
    same click. Backs the Activity tab of Admin > System Logs
    (RAG.views.admin_system_logs_view). Every row carries the
    request's IP and geolocation (city/region/country/lat/lon) when a
    request was in scope - see RAG.services.geolocation_service.
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

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Client IP of the request that triggered this event, via "
                   "activity_log_service.get_client_ip() - None for system-"
                   "initiated events with no request in scope.",
    )

    user_agent = models.TextField(
        blank=True,
        default="",
        help_text="Raw User-Agent header of the triggering request - parsed on "
                   "read by RAG.services.device_intelligence_service.parse_device() "
                   "into device type/browser/OS for login history, never parsed "
                   "at write time so a parser change never needs a backfill.",
    )

    city = models.CharField(max_length=100, blank=True, default="")
    region = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="", db_index=True)
    country_code = models.CharField(max_length=8, blank=True, default="")

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

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
        ("openrouter", "OpenRouter"),
        ("groq", "Groq"),
        ("gemini", "Gemini"),
    ]

    llm_provider = models.CharField(max_length=20, choices=LLM_PROVIDER_CHOICES, default="openrouter")

    # Off by default: the configured provider above must be the one
    # that actually answers, or the request fails outright - see
    # settings.LLM_FALLBACK_ENABLED and llm_client._build_chain() for
    # why this can never be a silent, invisible switch to another
    # provider unless an admin explicitly opts in here.
    enable_fallback = models.BooleanField(default=False)

    # Per-provider model selection - kept independent per provider
    # (rather than one shared "model" field) since a model name from
    # one provider is meaningless to another. See
    # RAG.services.llm_client.PROVIDER_REGISTRY for the curated
    # free-model choices the Settings page offers per provider; these
    # fields accept any string, so a value set directly via .eee is
    # never clobbered by the dropdown's curated list.
    openrouter_model = models.CharField(max_length=150, default="openai/gpt-oss-20b:free")
    groq_model = models.CharField(max_length=150, default="llama-3.1-8b-instant")
    gemini_model = models.CharField(max_length=150, default="gemini-2.0-flash")

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


class AITaskRun(models.Model):
    """
    One guided AI Task run (Select Task -> Select Documents -> Configure
    -> Run -> Review -> Export). Always processed on the in-process
    background thread pool (RAG.tasks.run_ai_task, dispatched via
    RAG.services.task_runner) - unlike document processing, there is no
    inline/synchronous path, since a run can span up to
    settings.AI_TASKS_MAX_DOCUMENTS documents.
    """

    class TaskType(models.TextChoices):
        ANALYZE = "analyze", "Analyze Documents"
        COMPARE = "compare", "Compare Documents"
        SUMMARIZE = "summarize", "Summarize Documents"
        EXTRACT = "extract", "Extract Information"
        VALIDATE = "validate", "Validate Against Reference Documents"
        FIND_SIMILAR = "find_similar", "Find Similar Documents"
        ORGANIZE = "organize", "Organize Documents"
        REPORT = "report", "Generate Reports"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ai_task_runs"
    )

    task_type = models.CharField(max_length=20, choices=TaskType.choices)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Task-specific options from the Configure step (criteria, "
                   "fields, similarity_threshold, ...) - shape depends on "
                   "task_type, validated by ai_tasks_engine_service, not the DB.",
    )

    document_count = models.PositiveIntegerField(
        default=0,
        help_text="Snapshot of the target-document count at creation time, "
                   "after the AI_TASKS_MAX_DOCUMENTS cap was enforced.",
    )

    error_message = models.TextField(blank=True, default="")

    cancel_requested = models.BooleanField(
        default=False,
        help_text="Set by ai_task_cancel() when a user stops a pending/running run. "
                   "execute_run() checks this in _call_llm_json() (the one choke point "
                   "every task handler's LLM calls go through) between calls and unwinds "
                   "to status=CANCELLED - so a stop takes effect within one LLM call's "
                   "worth of latency, not instantly, and never mid-write of a result row.",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_task_type_display()} ({self.id}) - {self.user.username}"


class AITaskRunDocument(models.Model):
    """
    Through model for AITaskRun's document set. TARGET documents are
    the ones being analyzed/compared/summarized/...; REFERENCE
    documents (a job description, a policy, a standard) are only used
    by Validate Against Reference Documents, and optionally Analyze
    Documents, to check TARGET documents against.
    """

    class Role(models.TextChoices):
        TARGET = "target", "Target"
        REFERENCE = "reference", "Reference"

    run = models.ForeignKey(
        AITaskRun, on_delete=models.CASCADE, related_name="run_documents"
    )

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="ai_task_run_memberships"
    )

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.TARGET
    )

    class Meta:
        unique_together = ("run", "document")
        indexes = [models.Index(fields=["run", "role"])]


class AITaskResult(models.Model):
    """
    One row per result item a run produces. `document` is NULL for a
    corpus-level result (Compare's overall diff narrative, Organize's
    per-group scheme, Generate Reports' final report body, Summarize's
    executive summary, Find Similar's per-cluster label) rather than a
    finding about one specific target document.

    SET_NULL (not CASCADE) on `document` so deleting a document later
    doesn't erase review history the user already exported - the row
    just loses its live document link and falls back to the `title`
    snapshot.
    """

    run = models.ForeignKey(AITaskRun, on_delete=models.CASCADE, related_name="results")

    document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_task_results",
    )

    rank = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Display order within its group - Analyze ranking, Organize "
                   "group index, Find Similar cluster index. NULL where no "
                   "ordering applies.",
    )

    score = models.FloatField(
        null=True, blank=True,
        help_text="Task-specific numeric score on a consistent 0-100 scale - "
                   "Analyze relevance, Validate compliance percent, Find "
                   "Similar/Organize similarity (cosine similarity * 100). "
                   "NULL where not applicable.",
    )

    title = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Document title snapshot for a per-document row, or a "
                   "heading (e.g. 'Executive Summary') for a corpus-level row.",
    )

    summary = models.TextField(
        blank=True, default="",
        help_text="LLM prose finding for this result, with inline [n] "
                   "citation markers per the citation_service.py convention.",
    )

    data = models.JSONField(
        default=dict, blank=True,
        help_text="Task-specific structured payload (extracted fields, "
                   "violations, combined table, report sections, ...). "
                   "Rendered generically by templates/ai_tasks/_result_row.html "
                   "based on which keys are present.",
    )

    citations = models.JSONField(
        default=list, blank=True,
        help_text="[{number, document, chunk_number, role}, ...] - the subset "
                   "of build_cited_context() source blocks this result's "
                   "summary actually cited.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run_id", "rank", "-score", "id"]
        indexes = [models.Index(fields=["run", "document"])]

    def __str__(self):
        return self.title or f"Result {self.id} for run {self.run_id}"


class AIRequestTrace(models.Model):
    """
    One row per Ask AI question or AI Task run - the shared execution
    trace both features write to (RAG.services.observability_service
    .save_trace() is the one function that creates these; nothing else
    should). Built from the same per-stage timing
    (RAG.services.perf.timed_stage() / RAG.services.trace.record_stage())
    and LLM call metadata (RAG.services.llm_client.get_last_llm_meta())
    both features already produce - this model is where that data
    becomes queryable instead of living only in console log lines.

    Exactly one of `query_log` / `ai_task_run` is set, matching `source`.
    AI Tasks gets one row per RUN, not per per-document LLM call (a run
    makes N+1 LLM calls) - `stages` is a list, so per-item granularity is
    an additive follow-up, not a redesign.
    """

    class Source(models.TextChoices):
        ASK_AI = "ask_ai", "Ask AI"
        AI_TASK = "ai_task", "AI Task"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    trace_id = models.CharField(max_length=32, unique=True, db_index=True)

    source = models.CharField(max_length=20, choices=Source.choices, db_index=True)

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_request_traces"
    )

    query_log = models.OneToOneField(
        QueryLog, on_delete=models.SET_NULL, null=True, blank=True, related_name="trace"
    )

    ai_task_run = models.OneToOneField(
        AITaskRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="trace"
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING, db_index=True)

    provider = models.CharField(max_length=50, blank=True, default="")

    model = models.CharField(max_length=100, blank=True, default="")

    providers_attempted = models.JSONField(
        default=list, blank=True,
        help_text="Ordered list of provider keys actually tried this request/run - "
                   "len() > 1 means a fallback happened.",
    )

    retry_count = models.PositiveIntegerField(default=0)

    prompt_tokens = models.PositiveIntegerField(null=True, blank=True)
    completion_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)

    llm_latency_ms = models.PositiveIntegerField(null=True, blank=True)

    time_to_first_token_ms = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Only populated for a streamed Ask AI answer.",
    )

    retrieved_chunks = models.PositiveIntegerField(default=0)

    citation_count = models.PositiveIntegerField(default=0)

    cache_hit = models.BooleanField(null=True, blank=True)

    stages = models.JSONField(
        default=list, blank=True,
        help_text="[{name, duration_ms, ...context}, ...] in execution order - "
                   "the same shape perf.timed_stage() already logs to console.",
    )

    total_duration_ms = models.PositiveIntegerField(default=0)

    bottleneck_stage = models.CharField(max_length=100, blank=True, default="")

    bottleneck_label = models.CharField(max_length=200, blank=True, default="")

    error_type = models.CharField(
        max_length=100, blank=True, default="",
        help_text="A short classified code (e.g. LLMTimeoutError, "
                   "AllProvidersFailedError) - never a raw exception message.",
    )

    error_message = models.TextField(
        blank=True, default="",
        help_text="Sanitized short message for support/debugging - must never "
                   "contain API keys, tokens, or a raw stack trace.",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.get_source_display()} trace {self.trace_id}"


class ErrorGroup(models.Model):
    """
    Deduplicated errors/warnings captured automatically from the app's
    existing logging calls (RAG.services.error_intelligence_service
    .ErrorCaptureHandler, wired into settings.LOGGING) - every
    logger.warning()/error()/exception() call already made throughout
    RAG/services/*.py, RAG/views.py, RAG/tasks.py (auth, documents,
    retrieval, LLM providers, background jobs, unhandled exceptions)
    flows into this model with zero changes to any of those call sites.

    One row per *distinct* error shape (see `fingerprint`), not one row
    per occurrence - an outage that logs the same warning 500 times
    increments one row's occurrence_count/last_seen/recent_occurrences
    rather than creating 500 rows. This is deliberately read-only
    observability, not a ticketing system - no resolved/acknowledged
    workflow.
    """

    fingerprint = models.CharField(
        max_length=64, unique=True, db_index=True,
        help_text="sha256(logger_name:level:error_type-or-normalized-message) - what groups occurrences together.",
    )

    logger_name = models.CharField(max_length=200, db_index=True, help_text='e.g. "RAG.services.llm_client", "django.request".')

    level = models.CharField(max_length=20, db_index=True, help_text="WARNING / ERROR / CRITICAL - matches the Python logging level name.")

    error_type = models.CharField(max_length=200, blank=True, default="", help_text="Exception class name, if the log call included exc_info - blank for a plain logger.warning() with no exception.")

    message = models.TextField(help_text="Redacted (see error_intelligence_service.redact_secrets()), truncated first-occurrence message - not a full traceback, by design (see the module docstring on what this deliberately doesn't store).")

    occurrence_count = models.PositiveIntegerField(default=1)

    first_seen = models.DateTimeField(auto_now_add=True)

    last_seen = models.DateTimeField(db_index=True)

    recent_occurrences = models.JSONField(
        default=list, blank=True,
        help_text="[{trace_id, timestamp}, ...] - the most recent occurrences only (capped), for correlating back to an AIRequestTrace or a specific request via RAG.services.trace's trace_id / the X-Request-ID response header.",
    )

    class Meta:
        ordering = ["-last_seen"]
        indexes = [
            models.Index(fields=["level", "last_seen"]),
            models.Index(fields=["logger_name", "last_seen"]),
        ]

    def __str__(self):
        return f"[{self.level}] {self.logger_name}: {self.message[:60]}"

    @property
    def severity(self):
        """
        Computed, not stored - a state machine (manually resolved/
        acknowledged errors) is explicitly out of scope; this is just
        "how alarming does this look right now" from level + recent
        volume, recomputed fresh every time it's read.
        """

        from django.utils import timezone

        if self.level == "CRITICAL":
            return "critical"

        recent_and_frequent = self.occurrence_count >= 10 and (timezone.now() - self.last_seen).total_seconds() < 3600

        if self.level == "ERROR" and recent_and_frequent:
            return "critical"

        if self.level == "ERROR":
            return "high"

        if recent_and_frequent:
            return "high"

        return "medium"


class UserProfile(models.Model):
    """
    Extended, enterprise-style profile data on top of auth.User - first/
    last name, username, email, date_joined, and last_login already live
    on User itself and are read directly rather than duplicated here; Role
    comes from the existing RBAC UserRole/Role models (see the "RBAC"
    section above); Account Status is User.is_active.

    Auto-created for every new User by the post_save signal in
    RAG/apps.py (_create_profile_for_new_user); views also call
    get_or_create() defensively for accounts that existed before this
    model did, the same "idempotent, safe to backfill lazily" approach
    RAG/management/commands/seed_rbac.py already uses for role
    assignment.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    headline = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text='One-line professional tagline, e.g. "AI Engineer | RAG Systems | Knowledge Intelligence".',
    )

    phone = models.CharField(max_length=30, blank=True, default="")

    department = models.CharField(max_length=100, blank=True, default="")
    job_title = models.CharField(max_length=150, blank=True, default="")

    employee_id = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Informational only - not DB-unique, since nothing else in "
                   "this project validates or looks up users by it yet.",
    )

    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_reports",
    )

    team = models.CharField(max_length=100, blank=True, default="")
    location = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Self-reported office/city location - distinct from the "
                   "IP-derived login location on ActivityLog.",
    )

    TIMEZONE_CHOICES_HELP = "IANA name (e.g. 'America/New_York') - free-form so any valid value saves even if the UI's curated <select> list doesn't cover it."
    timezone = models.CharField(max_length=50, blank=True, default="", help_text=TIMEZONE_CHOICES_HELP)

    # Curated IANA names for the profile form's <select> - not a Django
    # `choices` constraint (the field itself stays free-form, see the
    # help text above), just what the dropdown offers.
    COMMON_TIMEZONES = [
        "UTC",
        "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
        "America/Sao_Paulo", "America/Mexico_City", "America/Toronto",
        "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Madrid", "Europe/Moscow",
        "Africa/Cairo", "Africa/Lagos", "Africa/Johannesburg",
        "Asia/Dubai", "Asia/Karachi", "Asia/Kolkata", "Asia/Dhaka", "Asia/Bangkok",
        "Asia/Shanghai", "Asia/Tokyo", "Asia/Seoul", "Asia/Singapore",
        "Australia/Sydney", "Australia/Perth",
        "Pacific/Auckland",
    ]

    LANGUAGE_CHOICES = [
        ("en", "English"),
        ("es", "Spanish"),
        ("fr", "French"),
        ("de", "German"),
        ("hi", "Hindi"),
        ("zh", "Chinese"),
        ("ja", "Japanese"),
        ("pt", "Portuguese"),
        ("ar", "Arabic"),
    ]
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, blank=True, default="en")

    skills = models.JSONField(default=list, blank=True, help_text="List of plain strings.")
    certifications = models.JSONField(default=list, blank=True, help_text="List of plain strings.")

    linkedin_url = models.URLField(blank=True, default="")
    github_url = models.URLField(blank=True, default="")
    portfolio_url = models.URLField(blank=True, default="")

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        TEAM = "team", "Team"
        PRIVATE = "private", "Private"

    profile_visibility = models.CharField(
        max_length=10,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
        help_text="Stored preference only - there is no peer-facing profile "
                   "viewing page yet to enforce it against; Admin views "
                   "always see the full profile regardless (existing RBAC "
                   "bypass pattern, e.g. Role.has_permission).",
    )

    updated_at = models.DateTimeField(auto_now=True)

    email_verified = models.BooleanField(
        default=False,
        help_text="True once the account holder has completed email OTP "
                   "verification at signup (see RAG.services.otp_service). "
                   "Pre-existing accounts were backfilled to True by a "
                   "one-time data migration when this field was added - "
                   "only new signups actually go through OTP.",
    )

    def __str__(self):
        return f"{self.user.username}'s profile"


class EmailOTP(models.Model):
    """
    A one-time verification code emailed to a user - currently only used
    for signup verification, but `purpose` is namespaced so a future use
    (e.g. verifying a changed email address) needs no schema change.

    The code itself is never stored in plaintext - `code_hash` uses
    Django's own password hasher (django.contrib.auth.hashers.
    make_password()/check_password()), the same PBKDF2 machinery real
    passwords use, so this module introduces no new cryptographic code.
    The plaintext code exists only as a local variable in
    RAG.services.otp_service.generate_and_send_otp() and as an argument
    to the backgrounded email-send task - never logged, never returned
    in any response.
    """

    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Signup Verification"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_otps")

    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.SIGNUP)

    code_hash = models.CharField(max_length=128)

    attempt_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Incremented on every failed verify attempt against this "
                   "row - a durable, per-row cap (RAG.services.otp_service."
                   "MAX_OTP_ATTEMPTS) on top of the cache-based cross-row "
                   "rate limit in rate_limit_service.",
    )

    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "purpose", "is_used", "-created_at"])]

    def __str__(self):
        return f"{self.get_purpose_display()} OTP for {self.user.username}"


class Notification(models.Model):
    """
    A single recipient-facing notification - distinct from ActivityLog
    (a system-wide audit trail of what an *actor* did, admin-facing) and
    never populated from it. This is a per-user inbox: "X shared a
    document with you", read/unread, with an optional emailed copy.

    `notification_type` is namespaced "<area>.<event>" (e.g.
    "document.shared", "ai_task.completed", "account.password_changed")
    exactly like Permission.codename and ActivityLog.action, so new
    event types never require a schema change - just a new string and,
    optionally, an icon mapping in RAG.views._NOTIFICATION_ICONS.
    """

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")

    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Who caused this notification, if a specific user did (e.g. who shared the document). Blank for system-generated events.",
    )

    notification_type = models.CharField(max_length=50, db_index=True)

    title = models.CharField(max_length=200)
    message = models.CharField(max_length=500)

    data = models.JSONField(
        default=dict, blank=True,
        help_text="Extra structured payload for the event, e.g. {\"document_id\": 12, \"share_id\": 7}.",
    )

    action_url = models.CharField(
        max_length=500, blank=True, default="",
        help_text='Where the "Open" action navigates, e.g. a document URL. Computed at creation time via reverse() - never trusted as an authorization check by itself, the target view re-validates access.',
    )

    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Sanitized failure reason only (exception class name, not a raw traceback) - mirrors ErrorGroup's no-raw-stack-trace contract.",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"])]

    @property
    def category(self):
        """First segment of notification_type, e.g. "document" - derived, not stored, same pattern as Permission.namespace."""
        return self.notification_type.split(".")[0]

    def __str__(self):
        return f"{self.notification_type} -> {self.recipient.username}"


class NotificationPreference(models.Model):
    """
    Per-user email-notification opt-outs. In-app notifications are never
    disableable (the inbox is always the full record). "account" and
    "security" category notifications (password changed, new sign-in,
    email verified, ...) are never offered as toggleable and always
    email regardless of this row - see
    RAG.services.notification_service.ALWAYS_EMAIL_CATEGORIES.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="notification_preferences")

    disabled_email_categories = models.JSONField(
        default=list, blank=True,
        help_text="Category namespaces (e.g. \"document\", \"ai_task\") the user has opted out of *email* delivery for.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification preferences for {self.user.username}"
