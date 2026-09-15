"""Local identifier-preserving BM25-style TF; Qdrant supplies live IDF.

Fixed reference length avoids corpus-wide re-encoding as documents arrive.
This is a BM25-style approximation, not corpus-average-length BM25.
"""
from collections import Counter, defaultdict
from hashlib import blake2s
import re
from qdrant_client.models import SparseVector
from app.services.pid_identifiers import normalize_identifier, PID_PATTERNS
from app.services.tags import extract_tags

ENCODING = "industrial-bm25-v1"
STOP = set("a an the is are was were be been to of and or in on for with from by as this that what which how please find show containing".split())
TOKEN = re.compile(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*", re.I)
IDENTIFIER = re.compile(r"(?<![A-Z0-9-])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+[A-Z0-9]*(?:-[A-Z0-9]+)*(?![A-Z0-9-])")


def identifiers(text):
    normalized = normalize_identifier(text)
    return extract_tags(normalized, PID_PATTERNS) | {"technical_identifiers": sorted(set(IDENTIFIER.findall(normalized)))}


def terms(text):
    return [t for t in TOKEN.findall(normalize_identifier(text).lower()) if t not in STOP]


def term_index(term):
    return int.from_bytes(blake2s(term.encode("utf-8"), digest_size=4).digest(), "big")


def encode(text, query=False):
    counts = Counter(terms(text))
    length = sum(counts.values())
    values = defaultdict(float)
    for term, count in counts.items():
        weight = (3.0 if IDENTIFIER.fullmatch(term.upper()) else 1.0) if query else count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / 256))
        values[term_index(term)] += weight
    indices = sorted(values)
    return SparseVector(indices=indices, values=[values[i] for i in indices])


def index_text(metadata):
    # Include each supplemental term once only if absent from source text.
    content_terms = set(terms(metadata.content))
    extras = " ".join([metadata.title, *metadata.section_path, metadata.revision or "",
                       *metadata.equipment_tags, *metadata.instrument_tags, *metadata.line_numbers])
    return metadata.content + "\n" + " ".join(sorted(set(terms(extras)) - content_terms))
