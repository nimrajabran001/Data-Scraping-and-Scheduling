import os
import requests
import fitz

from rag_api.config import PDF_FOLDER, MARKDOWN_FOLDER


def download_pdf(url: str) -> str | None:
    """
    Download a PDF only if it does not already exist.
    """

    os.makedirs(PDF_FOLDER, exist_ok=True)

    filename = url.split("/")[-1].split("?")[0]

    if not filename.endswith(".pdf"):
        filename += ".pdf"

    pdf_path = os.path.join(PDF_FOLDER, filename)

    if os.path.exists(pdf_path):
        print(f"✓ PDF already exists: {filename}")
        return pdf_path

    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        with open(pdf_path, "wb") as f:
            f.write(response.content)

        print(f"✓ Downloaded {filename}")

        return pdf_path

    except Exception as e:
        print(f"❌ Failed downloading PDF: {e}")
        return None


def pdf_to_markdown(pdf_path: str) -> tuple[str, str]:
    """
    Convert PDF to Markdown.

    Returns
    -------
    markdown_text
    markdown_file_path
    """

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(pdf_path)

    os.makedirs(MARKDOWN_FOLDER, exist_ok=True)

    with fitz.open(pdf_path) as doc:

        markdown = []

        for page_number, page in enumerate(doc, start=1):

            markdown.append(f"# Page {page_number}\n")

            text = page.get_text("text")

            if text.strip():
                markdown.append(text.strip())

            markdown.append("\n")

    markdown_text = "\n".join(markdown).strip()

    if not markdown_text:
        raise ValueError("PDF contains no extractable text.")

    md_filename = (
        os.path.splitext(os.path.basename(pdf_path))[0]
        + ".md"
    )

    md_path = os.path.join(
        MARKDOWN_FOLDER,
        md_filename
    )

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_text)

    return markdown_text, md_path.replace("\\", "/")


def read_markdown(md_path: str) -> str:
    """
    Read markdown file.
    """

    with open(md_path, "r", encoding="utf-8") as f:
        return f.read()