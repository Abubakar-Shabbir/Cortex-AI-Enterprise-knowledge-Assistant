"""
Backfill processing_status for documents that existed before this
field was added. Without this, every already-processed document
(chunk_count > 0, uploaded under the old always-synchronous pipeline)
would default to PENDING - showing an "Embed" button that, if clicked,
would re-run process_uploaded_document() on a document that already
has chunks, creating duplicates rather than actually re-processing
anything (it has no "clear existing chunks first" step, since nothing
before this needed one).
"""

from django.db import migrations


def backfill_processing_status(apps, schema_editor):
    Document = apps.get_model("RAG", "Document")
    Document.objects.filter(chunk_count__gt=0).update(processing_status="completed")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('RAG', '0014_document_processing_status'),
    ]

    operations = [
        migrations.RunPython(backfill_processing_status, noop_reverse),
    ]
