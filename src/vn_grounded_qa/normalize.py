"""Vietnamese-aware text normalization helpers.

The MVP keeps segmentation dependency-free. A production deployment can replace
``segment_vi`` with a VnCoreNLP adapter without changing the store schema.
"""

from __future__ import annotations

import re
import os
import subprocess
import unicodedata
from typing import Iterable, List

TOKEN_RE = re.compile(r"[\w\-./]+", re.UNICODE)
SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    return SPACE_RE.sub(" ", text).strip().lower()


def ascii_fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    folded = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    folded = folded.replace("đ", "d").replace("Đ", "D")
    return normalize_text(folded)


def fallback_segment_vi(text: str) -> str:
    return " ".join(TOKEN_RE.findall(normalize_text(text)))


def segment_vi(text: str) -> str:
    """Return a searchable Vietnamese token stream.

    The default is a dependency-free fallback. Set
    ``VN_GROUNDED_QA_SEGMENTER`` to a command that accepts UTF-8 text on stdin
    and returns segmented text on stdout to use an external segmenter such as a
    VnCoreNLP wrapper.
    """

    command = os.environ.get("VN_GROUNDED_QA_SEGMENTER", "").strip()
    if not command:
        return fallback_segment_vi(text)
    try:
        completed = subprocess.run(
            command.split(),
            input=text,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return fallback_segment_vi(text)
    if completed.returncode != 0 or not completed.stdout.strip():
        return fallback_segment_vi(text)
    return normalize_text(completed.stdout)


def fts_query_terms(query: str) -> List[str]:
    terms = TOKEN_RE.findall(normalize_text(query))
    folded = TOKEN_RE.findall(ascii_fold(query))
    seen = set()
    out: List[str] = []
    for term in [*terms, *folded]:
        if term and term not in seen:
            seen.add(term)
            out.append(term)
    return out


def make_fts_query(query: str, extras: Iterable[str] = ()) -> str:
    terms = fts_query_terms(" ".join([query, *extras]))
    if not terms:
        return '""'
    return " OR ".join(f'"{term}"' for term in terms)
