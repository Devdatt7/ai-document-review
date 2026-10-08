"""Retrieval: find candidate evidence chunks for a claim using BM25.

This module ONLY finds candidates. It never decides if a claim is true or false,
and it never calls an LLM. Same input -> same output.
"""

import math
import re
from collections import Counter

from models import Claim, EvidenceChunk, EvidenceResult, Source

TOP_K = 3

# Standard BM25 settings.
K1 = 1.5  # how quickly repeating a word stops helping
B = 0.75  # how much long chunks are penalised

# Common words that would match almost every chunk and add noise.
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "of", "to", "in", "on",
    "at", "for", "by", "with", "and", "or", "as", "it", "its", "this", "that", "from",
    "has", "have", "had", "will", "can", "per", "our", "we", "any", "all", "not", "no",
}


# ---------- Step 1: chunking ----------

def chunk_source(source: Source) -> list[EvidenceChunk]:
    """Split a source into paragraph chunks with stable IDs like SRC1-P1-C1.

    P = page number (plain text counts as page 1), C = paragraph number on that page.
    A paragraph ends at a blank line. Only the whitespace around a paragraph is
    trimmed; its text is otherwise unchanged.
    """
    chunks = []
    for page in source.pages:
        page_number = page.page or 1
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page.text) if p.strip()]
        for number, paragraph in enumerate(paragraphs, start=1):
            chunks.append(
                EvidenceChunk(
                    source_id=source.source_id,
                    page=page.page,
                    chunk_id=f"{source.source_id}-P{page_number}-C{number}",
                    text=paragraph,
                )
            )
    return chunks


# ---------- Step 2: BM25 scoring ----------

def tokenize(text: str) -> list[str]:
    """Lowercase words and numbers; drop stopwords."""
    text = text.lower()
    # Make "50,000" and "50000" the same token so numbers match.
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    tokens = []
    for word in re.findall(r"\w+", text):
        if word in STOPWORDS:
            continue
        # Very simple plural handling: "refunds" -> "refund", "days" -> "day".
        if word.isalpha() and len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        tokens.append(word)
    return tokens


def bm25_scores(query_tokens: list[str], chunks_tokens: list[list[str]]) -> list[float]:
    """BM25 score of the query against every chunk (0.0 = no shared words)."""
    chunk_count = len(chunks_tokens)
    if chunk_count == 0:
        return []
    average_length = sum(len(t) for t in chunks_tokens) / chunk_count or 1.0

    # How many chunks contain each word (rare words matter more).
    chunks_with_word = Counter()
    for tokens in chunks_tokens:
        chunks_with_word.update(set(tokens))

    scores = []
    for tokens in chunks_tokens:
        word_counts = Counter(tokens)
        score = 0.0
        for word in sorted(set(query_tokens)):  # sorted -> same float sum every run
            count = word_counts[word]
            if count == 0:
                continue
            n = chunks_with_word[word]
            idf = math.log(1 + (chunk_count - n + 0.5) / (n + 0.5))  # never negative
            length_penalty = K1 * (1 - B + B * len(tokens) / average_length)
            score += idf * (count * (K1 + 1)) / (count + length_penalty)
        scores.append(score)
    return scores


# ---------- Step 3: the public functions ----------

def retrieve_evidence(claim: Claim, source: Source, top_k: int = TOP_K) -> list[EvidenceChunk]:
    """Return up to top_k chunks of `source` most related to the claim, best first.

    Chunks that share no words with the claim are never returned, so a claim with
    no useful evidence gives an empty list.
    """
    chunks = chunk_source(source)
    scores = bm25_scores(tokenize(claim.claim_text), [tokenize(c.text) for c in chunks])

    # Highest score first; ties keep the order they appear in the source.
    ranked = sorted(zip(chunks, scores), key=lambda pair: -pair[1])  # sorted() is stable
    return [
        chunk.model_copy(update={"score": round(score, 4)})
        for chunk, score in ranked[:top_k]
        if score > 0
    ]


def retrieve_for_claims(claims: list[Claim], source: Source) -> list[EvidenceResult]:
    """Run retrieval for every claim (one EvidenceResult per claim, same order)."""
    return [
        EvidenceResult(claim_id=claim.claim_id, evidence_chunks=retrieve_evidence(claim, source))
        for claim in claims
    ]


# ---------- Evaluation helper ----------

def recall_at_k(examples: list[tuple[Claim, str]], source: Source, k: int) -> float:
    """Share of labelled examples whose correct chunk is in the top k results.

    examples = [(claim, expected_chunk_id), ...]. Use k=1 for Recall@1, k=3 for Recall@3.
    """
    if not examples:
        return 0.0
    hits = 0
    for claim, expected_chunk_id in examples:
        found = [c.chunk_id for c in retrieve_evidence(claim, source, top_k=k)]
        if expected_chunk_id in found:
            hits += 1
    return hits / len(examples)
