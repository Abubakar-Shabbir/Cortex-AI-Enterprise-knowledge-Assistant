"""Categories - user-scoped single-valued grouping (see Category's model docstring)."""

from ..models import Category
from .document_library_service import unique_slug


def list_categories(user):
    return Category.objects.filter(user=user).order_by("name")


def create_category(user, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("Category name is required.")

    existing = Category.objects.filter(user=user, name__iexact=name).first()
    if existing:
        return existing

    return Category.objects.create(user=user, name=name, slug=unique_slug(Category, user, name))


def delete_category(user, category_id):
    Category.objects.filter(user=user, id=category_id).delete()


def set_document_category(user, document, category):
    if category is not None and category.user_id != user.id:
        raise ValueError("Cannot use another user's category.")
    document.category = category
    document.save(update_fields=["category"])
