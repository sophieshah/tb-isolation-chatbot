import os
import sys
import json
import re
import hashlib
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

import fitz  # PyMuPDF
import pdfplumber
import pytesseract

from PIL import Image

import spacy
import tiktoken

from sentence_transformers import SentenceTransformer

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PointStruct,
)

from dotenv import load_dotenv


# ============================================================
# Configuration
# ============================================================

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "documents")

EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    "intfloat/e5-large-v2"
)

CHUNK_SIZE = 450
CHUNK_OVERLAP = 75

IMAGE_DPI = 200

# E5-large-v2 embedding dimension
EMBEDDING_DIMENSION = 1024


# ============================================================
# Models
# ============================================================

print("Loading NLP model...", file=sys.stderr)

nlp = spacy.load("en_core_web_sm")

tokenizer = tiktoken.get_encoding("cl100k_base")

print(
    f"Loading embedding model: {EMBEDDING_MODEL_NAME}",
    file=sys.stderr
)

embedding_model = SentenceTransformer(
    EMBEDDING_MODEL_NAME
)


# ============================================================
# Qdrant
# ============================================================

qdrant = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)


def ensure_collection():
    """
    Create Qdrant collection if it does not already exist.
    """

    existing = [
        collection.name
        for collection in qdrant.get_collections().collections
    ]

    if COLLECTION_NAME not in existing:

        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=EMBEDDING_DIMENSION,
                distance=Distance.COSINE
            )
        )

        print(
            f"Created Qdrant collection: {COLLECTION_NAME}",
            file=sys.stderr
        )


# ============================================================
# Utility functions
# ============================================================

def normalize_text(text: str) -> str:
    """
    Clean PDF extraction artifacts.
    """

    if not text:
        return ""

    # Fix common PDF hyphenation
    text = re.sub(
        r"(\w)-\s*\n\s*(\w)",
        r"\1\2",
        text
    )

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)

    # Normalize excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def token_count(text: str) -> int:
    return len(tokenizer.encode(text))


def generate_id(document_id: str, page: int, index: int) -> str:
    raw = f"{document_id}:{page}:{index}"

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# Section detection
# ============================================================

def detect_section(text: str, current_section: str) -> str:

    lines = [
        line.strip()
        for line in text.split("\n")
        if line.strip()
    ]

    for line in lines:

        # Examples:
        #
        # 1 INTRODUCTION AND SCOPE OF GUIDELINES
        # 2 EXECUTIVE SUMMARY
        # 3 BACKGROUND AND RATIONALE

        if re.match(
            r"^\d+(\.\d+)*\s+[A-Z][A-Z\s\-—:&]+$",
            line
        ):
            return line

    return current_section


# ============================================================
# Sentence-aware chunking
# ============================================================

def split_into_sentences(text: str) -> List[str]:

    doc = nlp(text)

    return [
        sent.text.strip()
        for sent in doc.sents
        if sent.text.strip()
    ]


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP
) -> List[str]:

    sentences = split_into_sentences(text)

    chunks = []
    current = []
    current_tokens = 0

    for sentence in sentences:

        sentence_tokens = token_count(sentence)

        # If adding this sentence exceeds the limit,
        # finish the current chunk.
        if (
            current
            and current_tokens + sentence_tokens > chunk_size
        ):

            chunks.append(
                " ".join(current)
            )

            # Preserve sentence overlap
            overlap_sentences = []

            overlap_tokens = 0

            for previous in reversed(current):

                previous_tokens = token_count(previous)

                if overlap_tokens + previous_tokens > overlap:
                    break

                overlap_sentences.insert(
                    0,
                    previous
                )

                overlap_tokens += previous_tokens

            current = overlap_sentences

            current_tokens = overlap_tokens

        current.append(sentence)
        current_tokens += sentence_tokens

    if current:

        chunks.append(
            " ".join(current)
        )

    return chunks


# ============================================================
# Table extraction
# ============================================================

def table_to_markdown(table: List[List[str]]) -> str:

    if not table:
        return ""

    cleaned = []

    for row in table:

        row = [
            (cell or "").strip().replace("\n", " ")
            for cell in row
        ]

        cleaned.append(row)

    # Determine maximum number of columns
    column_count = max(
        len(row)
        for row in cleaned
    )

    normalized = []

    for row in cleaned:

        row = row + [""] * (
            column_count - len(row)
        )

        normalized.append(row)

    header = normalized[0]

    markdown = []

    markdown.append(
        "| " + " | ".join(header) + " |"
    )

    markdown.append(
        "| " +
        " | ".join(["---"] * column_count) +
        " |"
    )

    for row in normalized[1:]:

        markdown.append(
            "| " + " | ".join(row) + " |"
        )

    return "\n".join(markdown)


def extract_tables(pdf_path: str) -> Dict[int, List[Dict[str, Any]]]:

    tables_by_page = {}

    with pdfplumber.open(pdf_path) as pdf:

        for page_number, page in enumerate(
            pdf.pages,
            start=1
        ):

            tables = page.extract_tables()

            if not tables:
                continue

            page_tables = []

            for table_index, table in enumerate(tables):

                markdown = table_to_markdown(table)

                if not markdown.strip():
                    continue

                page_tables.append({
                    "table_index": table_index,
                    "content": markdown
                })

            if page_tables:
                tables_by_page[page_number] = page_tables

    return tables_by_page


# ============================================================
# Image extraction + OCR
# ============================================================

def extract_images(
    pdf_path: str,
    output_dir: Path
) -> Dict[int, List[Dict[str, Any]]]:

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    images_by_page = {}

    doc = fitz.open(pdf_path)

    for page_number, page in enumerate(
        doc,
        start=1
    ):

        images = page.get_images(
            full=True
        )

        page_images = []

        for image_index, image in enumerate(images):

            xref = image[0]

            try:

                image_data = doc.extract_image(xref)

                image_bytes = image_data["image"]

                extension = image_data["ext"]

                filename = (
                    f"page_{page_number}_"
                    f"image_{image_index}.{extension}"
                )

                image_path = (
                    output_dir / filename
                )

                with open(
                    image_path,
                    "wb"
                ) as f:
                    f.write(image_bytes)

                # OCR
                pil_image = Image.open(
                    image_path
                )

                ocr_text = pytesseract.image_to_string(
                    pil_image
                )

                page_images.append({
                    "image_index": image_index,
                    "path": str(image_path),
                    "ocr_text": normalize_text(
                        ocr_text
                    )
                })

            except Exception as e:

                print(
                    f"Image extraction failed "
                    f"on page {page_number}: {e}",
                    file=sys.stderr
                )

        if page_images:
            images_by_page[page_number] = page_images

    doc.close()

    return images_by_page


# ============================================================
# PDF page extraction
# ============================================================

def extract_pages(pdf_path: str):

    doc = fitz.open(pdf_path)

    pages = []

    for page_number, page in enumerate(
        doc,
        start=1
    ):

        text = page.get_text(
            "text"
        )

        pages.append({
            "page": page_number,
            "text": normalize_text(text)
        })

    doc.close()

    return pages


# ============================================================
# Build document chunks
# ============================================================

def build_chunks(
    pdf_path: str,
    document_id: str,
    document_name: str
):

    image_dir = (
        Path("output")
        / document_id
        / "images"
    )

    pages = extract_pages(
        pdf_path
    )

    tables = extract_tables(
        pdf_path
    )

    images = extract_images(
        pdf_path,
        image_dir
    )

    chunks = []

    chunk_index = 0

    current_section = "Unknown"

    for page_data in pages:

        page_number = page_data["page"]
        page_text = page_data["text"]

        if not page_text:
            continue

        current_section = detect_section(
            page_text,
            current_section
        )

        # ----------------------------------------------------
        # Normal text
        # ----------------------------------------------------

        text_chunks = chunk_text(
            page_text
        )

        for chunk in text_chunks:

            chunks.append({
                "id": generate_id(
                    document_id,
                    page_number,
                    chunk_index
                ),

                "document_id": document_id,
                "document_name": document_name,

                "chunk_index": chunk_index,

                "chunk_type": "text",

                "page": page_number,

                "section": current_section,

                "content": chunk,

                "metadata": {
                    "source": document_name,
                    "page": page_number,
                    "section": current_section,
                    "chunk_type": "text"
                }
            })

            chunk_index += 1

        # ----------------------------------------------------
        # Tables
        # ----------------------------------------------------

        for table in tables.get(
            page_number,
            []
        ):

            table_number = (
                table["table_index"]
            )

            content = table["content"]

            chunks.append({

                "id": generate_id(
                    document_id,
                    page_number,
                    chunk_index
                ),

                "document_id": document_id,
                "document_name": document_name,

                "chunk_index": chunk_index,

                "chunk_type": "table",

                "page": page_number,

                "section": current_section,

                "table_index": table_number,

                "content": content,

                "metadata": {
                    "source": document_name,
                    "page": page_number,
                    "section": current_section,
                    "chunk_type": "table",
                    "table_index": table_number
                }
            })

            chunk_index += 1

        # ----------------------------------------------------
        # Images
        # ----------------------------------------------------

        for image in images.get(
            page_number,
            []
        ):

            image_content = image[
                "ocr_text"
            ]

            if not image_content:
                image_content = (
                    "Image/figure extracted "
                    f"from page {page_number}."
                )

            chunks.append({

                "id": generate_id(
                    document_id,
                    page_number,
                    chunk_index
                ),

                "document_id": document_id,
                "document_name": document_name,

                "chunk_index": chunk_index,

                "chunk_type": "image",

                "page": page_number,

                "section": current_section,

                "image_index": image[
                    "image_index"
                ],

                "image_path": image[
                    "path"
                ],

                "content": image_content,

                "metadata": {
                    "source": document_name,
                    "page": page_number,
                    "section": current_section,
                    "chunk_type": "image",
                    "image_index": image[
                        "image_index"
                    ],
                    "image_path": image[
                        "path"
                    ]
                }
            })

            chunk_index += 1

    return chunks


# ============================================================
# E5-large embedding
# ============================================================

def embed_chunks(
    chunks: List[Dict[str, Any]]
):

    texts = []

    for chunk in chunks:

        # E5 models expect "passage:" for documents
        text = (
            "passage: "
            + chunk["content"]
        )

        texts.append(text)

    embeddings = embedding_model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True
    )

    for chunk, embedding in zip(
        chunks,
        embeddings
    ):

        chunk["embedding"] = embedding.tolist()

    return chunks


# ============================================================
# Upload to Qdrant
# ============================================================

def upload_to_qdrant(
    chunks: List[Dict[str, Any]]
):

    points = []

    for chunk in chunks:

        payload = {
            "document_id": chunk[
                "document_id"
            ],

            "document_name": chunk[
                "document_name"
            ],

            "chunk_index": chunk[
                "chunk_index"
            ],

            "chunk_type": chunk[
                "chunk_type"
            ],

            "page": chunk[
                "page"
            ],

            "section": chunk[
                "section"
            ],

            "content": chunk[
                "content"
            ],

            "metadata": chunk[
                "metadata"
            ]
        }

        # Add optional metadata
        if "table_index" in chunk:
            payload["table_index"] = (
                chunk["table_index"]
            )

        if "image_index" in chunk:
            payload["image_index"] = (
                chunk["image_index"]
            )

        if "image_path" in chunk:
            payload["image_path"] = (
                chunk["image_path"]
            )

        points.append(
            PointStruct(
                id=chunk["id"],
                vector=chunk["embedding"],
                payload=payload
            )
        )

    # Upload in batches
    batch_size = 64

    for i in range(
        0,
        len(points),
        batch_size
    ):

        batch = points[
            i:i + batch_size
        ]

        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=batch
        )

        print(
            f"Uploaded {min(i + batch_size, len(points))}"
            f"/{len(points)} chunks",
            file=sys.stderr
        )


# ============================================================
# Main ingestion pipeline
# ============================================================

def ingest_document(pdf_path: str):

    pdf_path = Path(pdf_path)

    document_name = pdf_path.name

    document_id = hashlib.sha1(
        str(pdf_path.resolve()).encode()
    ).hexdigest()

    print(
        f"Processing: {document_name}",
        file=sys.stderr
    )

    ensure_collection()

    print(
        "Extracting document structure...",
        file=sys.stderr
    )

    chunks = build_chunks(
        str(pdf_path),
        document_id,
        document_name
    )

    print(
        f"Created {len(chunks)} chunks",
        file=sys.stderr
    )

    print(
        "Generating E5 embeddings...",
        file=sys.stderr
    )

    chunks = embed_chunks(
        chunks
    )

    print(
        "Uploading to Qdrant...",
        file=sys.stderr
    )

    upload_to_qdrant(
        chunks
    )

    # Don't return embeddings to Node
    # because they can be very large.
    response_chunks = []

    for chunk in chunks:

        response_chunks.append({
            "id": chunk["id"],
            "document_id": chunk[
                "document_id"
            ],
            "page": chunk["page"],
            "section": chunk["section"],
            "chunk_type": chunk[
                "chunk_type"
            ]
        })

    result = {
        "success": True,
        "document_id": document_id,
        "document_name": document_name,
        "chunks": len(chunks),
        "chunk_types": {
            "text": sum(
                c["chunk_type"] == "text"
                for c in chunks
            ),
            "table": sum(
                c["chunk_type"] == "table"
                for c in chunks
            ),
            "image": sum(
                c["chunk_type"] == "image"
                for c in chunks
            )
        },
        "items": response_chunks
    }

    # IMPORTANT:
    # stdout contains ONLY JSON so Node.js
    # can safely parse it.
    print(
        json.dumps(result)
    )


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "pdf",
        help="Path to PDF document"
    )

    args = parser.parse_args()

    ingest_document(
        args.pdf
    )