import os

from django.conf import settings


# ==========================================
# Validate File Extension
# ==========================================

def validate_extension(file):

    extension = os.path.splitext(
        file.name
    )[1].lower()

    if extension not in settings.ALLOWED_FILE_EXTENSIONS:

        raise ValueError(

            f"Unsupported file type: {extension}"

        )


# ==========================================
# Validate File Size
# ==========================================

def validate_file_size(file):

    if file.size > settings.MAX_FILE_SIZE:

        max_mb = settings.MAX_FILE_SIZE // (1024 * 1024)

        raise ValueError(

            f"File size exceeds {max_mb} MB."

        )


# ==========================================
# Validate Empty File
# ==========================================

def validate_empty_file(file):

    if file.size == 0:

        raise ValueError(

            "Uploaded file is empty."

        )


# ==========================================
# Basic Corruption Check
# ==========================================

def validate_file_readable(file):

    try:

        file.read(1024)

        file.seek(0)

    except Exception:

        raise ValueError(

            "File appears to be corrupted."

        )


# ==========================================
# Validate File Name
# ==========================================

def validate_file_name(file):

    if not file.name.strip():

        raise ValueError(

            "Invalid file name."

        )


# ==========================================
# Master Validation Function
# ==========================================

def validate_document(file):

    validate_file_name(file)

    validate_extension(file)

    validate_file_size(file)

    validate_empty_file(file)

    validate_file_readable(file)

    return True