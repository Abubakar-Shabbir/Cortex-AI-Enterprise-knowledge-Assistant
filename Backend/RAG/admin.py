from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied

from .models import (
    ADMIN_ROLE_SLUG,
    Category,
    ChunkEmbedding,
    Collection,
    CollectionDocument,
    Document,
    DocumentAccessLog,
    DocumentChunk,
    DocumentShare,
    DocumentVersion,
    EmailOTP,
    Entity,
    EntityMention,
    Favorite,
    Notification,
    NotificationPreference,
    Permission,
    QueryLog,
    Relationship,
    Role,
    Tag,
    UserRole,
)
from .services.activity_log_service import log_activity
from .services.permission_service import (
    can_actor_assign_role,
    can_actor_manage_target_user,
    get_assignable_roles,
    get_user_permission_set,
    is_admin,
    user_has_permission,
)


class UserRoleInline(admin.StackedInline):
    """
    Lets staff assign/change a user's RBAC role right on the built-in
    Django Admin User change page, in addition to the custom
    /admin/users/ portal (RAG.views.admin_users_view) - both write the
    same UserRole row, so they can never drift apart, and both are
    routed through the exact same privilege-escalation guards in
    RAG/services/permission_service.py (see that module's
    "Privilege-escalation guards" section): the role dropdown here
    only ever lists what get_assignable_roles() allows, and
    UserAdmin.save_formset below re-validates on save regardless of
    what the dropdown showed, so a crafted POST can't bypass it either.
    """

    model = UserRole
    fk_name = "user"
    extra = 1
    max_num = 1
    can_delete = False
    readonly_fields = ("assigned_by", "assigned_at")
    verbose_name = "RBAC role assignment"
    verbose_name_plural = "RBAC role assignment"

    # Same is_admin() gate as RBACAdminOnlyMixin (not reused directly -
    # StackedInline's permission signature differs from ModelAdmin's) -
    # a Django is_staff account viewing the User change page shouldn't
    # see or edit RBAC role assignments unless the app's own RBAC says
    # they're an Admin, regardless of what Django's own auth
    # permissions happen to grant them.
    def has_view_permission(self, request, obj=None):
        return is_admin(request.user)

    def has_add_permission(self, request, obj=None):
        return is_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin(request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "role":
            assignable_ids = [role.id for role in get_assignable_roles(request.user)]
            kwargs["queryset"] = Role.objects.filter(id__in=assignable_ids)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class UserAdmin(DjangoUserAdmin):
    inlines = (*DjangoUserAdmin.inlines, UserRoleInline)
    list_display = (*DjangoUserAdmin.list_display, "get_role")

    @admin.display(description="RBAC role")
    def get_role(self, obj):
        assignment = getattr(obj, "role_assignment", None)
        return assignment.role.name if assignment else "—"

    def save_formset(self, request, form, formset, change):
        if formset.model is not UserRole:
            return super().save_formset(request, form, formset, change)

        instances = formset.save(commit=False)
        for instance in instances:

            if not can_actor_manage_target_user(request.user, instance.user) or not can_actor_assign_role(request.user, instance.role):
                log_activity(
                    actor=request.user,
                    action="security.privilege_escalation_blocked",
                    description=(
                        f'{request.user.username} tried to set "{instance.user.username}" to '
                        f'{instance.role.name} via Django Admin - blocked'
                    ),
                    request=request,
                )
                raise PermissionDenied(f'You don\'t have permission to assign "{instance.role.name}" to this user.')

            is_new = instance.pk is None
            if is_new:
                instance.assigned_by = request.user
            instance.save()
            log_activity(
                actor=request.user,
                action="user.role_changed",
                description=f'"{instance.user.username}" set to {instance.role.name} by {request.user.username}',
                request=request,
            )
        formset.save_m2m()


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


class RBACAdminOnlyMixin:
    """
    Restricts a Django Admin page to this app's own Admin role
    (permission_service.is_admin), not Django's is_staff/is_superuser.
    Role/Permission/UserRole are the RBAC system itself - the one place
    a Django `is_superuser=True` account (an ops/deploy account,
    createsuperuser, ...) unconditionally bypassing ModelAdmin's
    default permission checks would matter most, since it would let
    such an account view every user's role assignment and the full
    permission catalog regardless of what their own RBAC role (if any)
    actually grants. The privilege-escalation writes below were already
    guarded (see RoleAdmin.save_related / UserRoleAdmin.save_model) -
    this closes the matching read/visibility gap.
    """

    def has_module_permission(self, request):
        return is_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin(request.user)

    def has_add_permission(self, request):
        return is_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin(request.user)


@admin.register(Role)
class RoleAdmin(RBACAdminOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "is_system", "created_at")
    list_filter = ("is_system",)
    search_fields = ("name", "slug")
    filter_horizontal = ("permissions",)
    prepopulated_fields = {"slug": ("name",)}

    def save_related(self, request, form, formsets, change):
        """
        Applies the exact same privilege-escalation scoping as
        RAG.views.admin_roles_view's update_permissions action, so
        Django Admin can't be used to bypass what the custom portal
        already refuses - see permission_service.
        compute_updated_role_permissions for the full rationale.
        Implemented directly here (not by calling that function)
        because by the time save_related runs, Django's own m2m save
        has *already* applied whatever the permissions widget
        submitted - the "original, before this edit" set has to be
        captured before calling super().
        """

        role = form.instance
        original_permissions = set(role.permissions.values_list("codename", flat=True)) if role.pk else set()

        super().save_related(request, form, formsets, change)

        if role.slug == ADMIN_ROLE_SLUG:
            # Admin always has every permission by design
            # (Role.has_permission's bypass) - force the M2M table
            # back to the full set no matter what was submitted.
            role.permissions.set(Permission.objects.all())
            return

        if not is_admin(request.user):
            submitted = set(role.permissions.values_list("codename", flat=True))
            actor_perms = get_user_permission_set(request.user)
            outside_actor_scope = original_permissions - actor_perms
            within_actor_scope_submitted = submitted & actor_perms
            final = outside_actor_scope | within_actor_scope_submitted

            if final != submitted:
                log_activity(
                    actor=request.user,
                    action="security.privilege_escalation_blocked",
                    description=(
                        f'{request.user.username} tried to grant "{role.name}" permissions beyond their own '
                        f"via Django Admin - blocked"
                    ),
                    request=request,
                )
                role.permissions.set(Permission.objects.filter(codename__in=final))


@admin.register(Permission)
class PermissionAdmin(RBACAdminOnlyMixin, admin.ModelAdmin):
    list_display = ("codename", "name", "namespace")
    search_fields = ("codename", "name", "description")


@admin.register(UserRole)
class UserRoleAdmin(RBACAdminOnlyMixin, admin.ModelAdmin):
    list_display = ("user", "role", "assigned_by", "assigned_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user", "role")
    readonly_fields = ("assigned_by", "assigned_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "role":
            assignable_ids = [role.id for role in get_assignable_roles(request.user)]
            kwargs["queryset"] = Role.objects.filter(id__in=assignable_ids)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):

        if not can_actor_manage_target_user(request.user, obj.user) or not can_actor_assign_role(request.user, obj.role):
            log_activity(
                actor=request.user,
                action="security.privilege_escalation_blocked",
                description=f'{request.user.username} tried to set "{obj.user.username}" to {obj.role.name} via Django Admin - blocked',
                request=request,
            )
            raise PermissionDenied(f'You don\'t have permission to assign "{obj.role.name}" to this user.')

        if not change:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)
        log_activity(
            actor=request.user,
            action="user.role_changed",
            description=f'"{obj.user.username}" set to {obj.role.name} by {request.user.username}',
            request=request,
        )


class RBACScopedModelAdmin(admin.ModelAdmin):
    """
    Base for ModelAdmins over data that spans every user's account
    (documents, their chunks/embeddings, query logs, the knowledge
    graph). Django's default ModelAdmin permission checks only look
    at is_staff/is_superuser - entirely separate from this project's
    custom RBAC (Role/Permission/UserRole) - so an org's Django staff
    account (e.g. an ops/deploy account, or any `createsuperuser`
    account) would otherwise browse every user's private data
    regardless of what their RBAC role actually grants. These route
    through the same permission_service codenames the rest of the app
    uses instead, and are read-only here by default: none of this
    data has a legitimate "hand-edit it in Django Admin" workflow -
    documents/chunks/embeddings/entities/relationships are all
    pipeline-generated, and query logs are an audit trail, not
    editable records. Mutations belong to the app's own views
    (document_delete, etc.), which already carry the right cascades
    and activity logging.
    """

    view_permission = None

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_view_permission(self, request, obj=None):
        return bool(self.view_permission) and user_has_permission(request.user, self.view_permission)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Document)
class DocumentAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("title", "user", "file_type", "chunk_count", "file_size", "uploaded_at")
    list_filter = ("file_type",)
    search_fields = ("title", "user__username")

    def has_delete_permission(self, request, obj=None):
        return user_has_permission(request.user, "documents.delete_any")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("document", "chunk_number", "created_at")
    list_filter = ("document",)


@admin.register(ChunkEmbedding)
class ChunkEmbeddingAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("chunk", "embedding_model", "created_at")
    list_filter = ("embedding_model",)


@admin.register(QueryLog)
class QueryLogAdmin(RBACScopedModelAdmin):
    """
    Metadata (owner/confidence/response time/search method/timestamp)
    is gated behind "queries.view_all_logs", same as Admin > Queries
    in the app itself. The actual conversation content (question,
    answer, retrieved sources) is a further-gated tier behind
    "queries.view_content" - a holder of only "queries.view_all_logs"
    sees this list with content columns/search removed entirely,
    never blanked-but-present, so it can't be recovered from the page
    source. Mirrors RAG.views.admin_queries_view's redaction.
    """

    view_permission = "queries.view_all_logs"
    list_filter = ("user", "search_method")

    def get_list_display(self, request):
        if user_has_permission(request.user, "queries.view_content"):
            return ("user", "question", "confidence", "response_time_ms", "created_at")
        return ("user", "confidence", "response_time_ms", "created_at")

    def get_search_fields(self, request):
        if user_has_permission(request.user, "queries.view_content"):
            return ("question", "answer")
        return ()

    def get_fields(self, request, obj=None):
        if user_has_permission(request.user, "queries.view_content"):
            return ("user", "question", "answer", "sources", "search_method", "confidence", "response_time_ms", "created_at")
        return ("user", "search_method", "confidence", "response_time_ms", "created_at")

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj)


@admin.register(Entity)
class EntityAdmin(RBACScopedModelAdmin):
    # No delegated cross-user permission exists for the knowledge
    # graph (unlike documents/queries) since the app itself has no
    # Admin-facing Knowledge Base surface - restrict to the Admin
    # role outright rather than inventing a permission nothing else
    # in the UI grants or checks.
    view_permission = None
    list_display = ("display_name", "entity_type", "user", "mention_count", "created_at")
    list_filter = ("entity_type",)
    search_fields = ("name", "display_name", "user__username")

    def has_view_permission(self, request, obj=None):
        return is_admin(request.user)


@admin.register(Relationship)
class RelationshipAdmin(RBACScopedModelAdmin):
    list_display = ("source", "relation_type", "target", "weight", "user", "created_at")
    list_filter = ("relation_type",)
    search_fields = ("source__display_name", "target__display_name")

    def has_view_permission(self, request, obj=None):
        return is_admin(request.user)


@admin.register(EntityMention)
class EntityMentionAdmin(RBACScopedModelAdmin):
    list_display = ("entity", "chunk", "created_at")
    list_filter = ("entity",)

    def has_view_permission(self, request, obj=None):
        return is_admin(request.user)


@admin.register(Category)
class CategoryAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("name", "user", "created_at")
    search_fields = ("name", "user__username")


@admin.register(Tag)
class TagAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("name", "user", "created_at")
    search_fields = ("name", "user__username")


@admin.register(Collection)
class CollectionAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("name", "user", "created_at")
    search_fields = ("name", "user__username")


@admin.register(CollectionDocument)
class CollectionDocumentAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("collection", "document", "added_at")


@admin.register(Favorite)
class FavoriteAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("user", "document", "created_at")


@admin.register(DocumentVersion)
class DocumentVersionAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("document", "version_number", "file_type", "replaced_at")


@admin.register(DocumentShare)
class DocumentShareAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("document", "shared_with_user", "shared_with_role", "shared_by", "created_at")


@admin.register(DocumentAccessLog)
class DocumentAccessLogAdmin(RBACScopedModelAdmin):
    view_permission = "documents.view_all"
    list_display = ("user", "document", "accessed_at")


@admin.register(Notification)
class NotificationAdmin(RBACScopedModelAdmin):
    view_permission = "notifications.view_all"
    list_display = ("recipient", "notification_type", "title", "is_read", "email_sent", "created_at")
    list_filter = ("notification_type", "is_read", "email_sent")
    search_fields = ("recipient__username", "title", "message")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(RBACScopedModelAdmin):
    view_permission = "notifications.view_all"
    list_display = ("user", "disabled_email_categories", "updated_at")


@admin.register(EmailOTP)
class EmailOTPAdmin(RBACScopedModelAdmin):
    # users.view_all, not notifications.view_all - this is account-
    # verification data, not a notification. Only code_hash is ever
    # shown/stored (see EmailOTP's own docstring) - never the raw code.
    view_permission = "users.view_all"
    list_display = ("user", "purpose", "attempt_count", "is_used", "created_at", "expires_at")
    list_filter = ("purpose", "is_used")
    readonly_fields = [f.name for f in EmailOTP._meta.fields]
