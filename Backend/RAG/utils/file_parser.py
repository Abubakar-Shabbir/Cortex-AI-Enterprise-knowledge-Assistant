import os

from pypdf import PdfReader
from docx import Document as DocxDocument


def extract_text(file_path):
    """
    Extract text from supported document formats.

    Supported:
    - PDF
    - DOCX
    - TXT
    """

    extension = os.path.splitext(file_path)[1].lower()

    if extension == ".pdf":

        reader = PdfReader(file_path)

        text = ""

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

        return text

    elif extension == ".docx":

        document = DocxDocument(file_path)

        return "\n".join(
            paragraph.text
            for paragraph in document.paragraphs
        )

    elif extension == ".txt":

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:

            return file.read()

    raise ValueError(
        f"Unsupported file format: {extension}"
    )