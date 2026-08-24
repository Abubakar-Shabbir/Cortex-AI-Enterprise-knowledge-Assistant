import os
from pathlib import Path


def extract_metadata(file):
    """
    Extract basic metadata
    from uploaded file.
    """

    # -------------------------
    # File Name
    # -------------------------

    file_name = file.name

    # -------------------------
    # File Extension
    # -------------------------

    file_extension = (
        Path(file_name)
        .suffix
        .lower()
        .replace(".", "")
    )

    # -------------------------
    # File Size
    # -------------------------

    file_size = file.size

    # -------------------------
    # Return Metadata
    # -------------------------

    return {

        "file_name": file_name,

        "file_type": file_extension,

        "file_size": file_size,

    }