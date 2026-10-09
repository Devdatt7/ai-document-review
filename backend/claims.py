"""Claim extraction: DOCUMENT -> SENTENCES -> CLAIMS. Nothing more."""

import re

from pydantic import BaseModel, Field, ValidationError

from llm import LLMError, LLMOutputError, ask_llm_json
from models import Claim, ClaimExtractionResult, ClaimType, Sentence


# ---------- Step 1: sentences (plain Python, the LLM never makes IDs) ----------

def split_sentences(document_text: str) -> list[Sentence]:
    """Split text into sentences and give each a stable ID: S1, S2, S3..."""
    sentences = []
    # A new line always starts a new sentence; inside a line, split after . ! ? + space.
    for line in document_text.splitlines():
        for part in re.split(r"(?<=[.!?])\s+", line.strip()):
            if part:
                sentences.append(Sentence(sentence_id=f"S{len(sentences) + 1}", text=part))
    return sentences


# ---------- Step 2: claims (Gemini) ----------

# What we ask Gemini to return. claim_id is NOT here: Python adds it afterwards.
class _LLMClaim(BaseModel):
    sentence_id: str
    claim_text: str = Field(min_length=1)
    claim_type: ClaimType


class _LLMClaims(BaseModel):
    claims: list[_LLMClaim]


PROMPT = """You find meaningful claims in sentences from an AI-written document.
A meaningful claim is a factual or decision-relevant statement that could be checked
against a source (amounts, dates, policies, legal or regulatory statements,
commitments or guarantees, named entities, sensitive data).

Rules:
- Use ONLY the sentence_id values given below. Never invent IDs.
- A sentence may have zero, one or several claims. Skip sentences with nothing meaningful.
- claim_text must stay faithful to the sentence. Do not change its meaning or add facts.
- claim_type must be one of: {types}.

SENTENCES:
{sentences}
"""


def _build_prompt(sentences: list[Sentence]) -> str:
    lines = "\n".join(f"{s.sentence_id}: {s.text}" for s in sentences)
    return PROMPT.format(types=", ".join(t.value for t in ClaimType), sentences=lines)


def _ask_for_claims(sentences: list[Sentence]) -> list[Claim]:
    """One Gemini call. Raises LLMError if the answer is unusable."""
    answer = ask_llm_json(_build_prompt(sentences), _LLMClaims)

    known_ids = {s.sentence_id for s in sentences}
    claims = []
    for item in answer.claims:
        if item.sentence_id not in known_ids:
            raise LLMOutputError(f"Gemini returned an unknown sentence id '{item.sentence_id}'.")
        try:
            claims.append(
                Claim(
                    claim_id=f"C{len(claims) + 1}",
                    sentence_id=item.sentence_id,
                    claim_text=item.claim_text.strip(),
                    claim_type=item.claim_type,
                )
            )
        except ValidationError:
            raise LLMOutputError("Gemini returned an invalid claim.") from None
    return claims


def extract_claims(document_text: str) -> ClaimExtractionResult:
    sentences = split_sentences(document_text)
    if not sentences:
        return ClaimExtractionResult(sentences=[], claims=[])

    # Try once more if the first answer is unusable; never invent claims on failure.
    try:
        claims = _ask_for_claims(sentences)
    except LLMOutputError:
        claims = _ask_for_claims(sentences)

    return ClaimExtractionResult(sentences=sentences, claims=claims)
