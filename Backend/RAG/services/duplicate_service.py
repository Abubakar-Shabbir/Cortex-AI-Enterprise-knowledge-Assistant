import hashlib

from ..models import Document


def calculate_file_hash(file):
    """
    Calculate SHA-256 hash
    of uploaded file.
    """

    sha256 = hashlib.sha256()

    for chunk in file.chunks():
        sha256.update(chunk)

    file.seek(0)

    return sha256.hexdigest()


def check_duplicate(user, file):
    """
    Check whether the uploaded
    document already exists.
    """

    file_hash = calculate_file_hash(file)

    exists = Document.objects.filter(

        user=user,
        file_hash=file_hash

    ).exists()

    return exists, file_hash