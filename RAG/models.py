from django.db import models
from django.contrib.auth.models import User



class Document(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
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


    def __str__(self):
        return self.title




class DocumentChunk(models.Model):

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks"
    )


    content = models.TextField()


    chunk_number = models.IntegerField()


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):

        return f"{self.document.title} - Chunk {self.chunk_number}"