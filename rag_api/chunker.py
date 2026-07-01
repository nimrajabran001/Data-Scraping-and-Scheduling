import re
from typing import List


def split_sentences(text: str) -> List[str]:
    """
    Split text into sentences while preserving punctuation.
    """
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    return re.split(r"(?<=[.!?])\s+", text)


def smart_chunk(
    text: str,
    size: int = 800,
    overlap: int = 150
) -> List[str]:
   

    sentences = split_sentences(text)

    if not sentences:
        return []

    chunks = []

    current_chunk = ""

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        # Sentence alone exceeds chunk size
        if len(sentence) >= size:

            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            for i in range(0, len(sentence), size):
                chunks.append(sentence[i:i + size])

            continue

        # Fits in current chunk
        if len(current_chunk) + len(sentence) + 1 <= size:

            if current_chunk:
                current_chunk += " "

            current_chunk += sentence

        else:

            chunks.append(current_chunk.strip())

            # -------- overlap --------

            overlap_text = current_chunk[-overlap:]

            split_pos = overlap_text.find(" ")

            if split_pos != -1:
                overlap_text = overlap_text[split_pos + 1:]

            current_chunk = overlap_text + " " + sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks