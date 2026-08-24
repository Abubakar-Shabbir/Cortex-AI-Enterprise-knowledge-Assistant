from django.conf import settings

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter
)

from .text_extractor import extract_text
from .semantic_chunk_service import semantic_chunk


def process_document(file_path):
    """
    Enterprise Document Processing Pipeline

    Steps
    -----
    1. Extract Text
    2. Clean Text
    3. Recursive Chunking
    4. Semantic Chunking
    5. Return Final Chunks
    """

    # -------------------------
    # Extract Text
    # -------------------------

    text = extract_text(
        file_path
    )

    # -------------------------
    # Clean Text
    # -------------------------

    text = " ".join(
        text.split()
    )

    # -------------------------
    # Recursive Chunking
    # -------------------------

    recursive_splitter = (
        RecursiveCharacterTextSplitter(

            chunk_size=settings.CHUNK_SIZE,

            chunk_overlap=settings.CHUNK_OVERLAP,

            separators=[
                "\n\n",
                "\n",
                ". ",
                "? ",
                "! ",
                ";",
                ",",
                " ",
                ""
            ]
        )
    )

    recursive_chunks = (
        recursive_splitter.split_text(
            text
        )
    )

    # -------------------------
    # Semantic Chunking
    # -------------------------

    final_chunks = []

    for chunk in recursive_chunks:

        semantic_chunks = semantic_chunk(
            chunk
        )

        final_chunks.extend(
            semantic_chunks
        )

    # -------------------------
    # Remove Empty Chunks
    # -------------------------

    final_chunks = [

        chunk.strip()

        for chunk in final_chunks

        if chunk.strip()

    ]

    return final_chunks