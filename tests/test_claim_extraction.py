import pytest
from fastapi.testclient import TestClient

import claims
from llm import LLMError
from main import app
from models import ClaimType


def fake_llm(*items):
    """Build a pretend Gemini answer: items are (sentence_id, claim_text, claim_type)."""
    answer = claims._LLMClaims(
        claims=[
            claims._LLMClaim(sentence_id=s, claim_text=t, claim_type=c) for s, t, c in items
        ]
    )
    return lambda prompt, schema: answer


# ---------- sentence splitting ----------

def test_empty_document_makes_no_llm_call(monkeypatch):
    def boom(prompt, schema):
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr(claims, "ask_llm_json", boom)
    for text in ["", "   \n  \n"]:
        result = claims.extract_claims(text)
        assert result.sentences == [] and result.claims == []


def test_one_sentence():
    sentences = claims.split_sentences("Refunds are available within 30 days.")
    assert [(s.sentence_id, s.text) for s in sentences] == [
        ("S1", "Refunds are available within 30 days.")
    ]


def test_multiple_sentences_and_lines():
    text = "First one. Second one!\n\nThird one?\nFourth one"
    sentences = claims.split_sentences(text)
    assert [s.text for s in sentences] == ["First one.", "Second one!", "Third one?", "Fourth one"]


def test_sentence_ids_are_stable_and_numbered_by_python():
    text = "A is true. B is true. C is true."
    first = claims.split_sentences(text)
    second = claims.split_sentences(text)
    assert [s.sentence_id for s in first] == ["S1", "S2", "S3"]
    assert first == second


def test_decimals_and_rupee_amounts_are_not_split():
    sentences = claims.split_sentences("The maximum reimbursement is ₹50,000.5 today. Next.")
    assert len(sentences) == 2


# ---------- claim extraction with a fake LLM ----------

def test_valid_response_gets_python_claim_ids(monkeypatch):
    monkeypatch.setattr(
        claims,
        "ask_llm_json",
        fake_llm(("S1", "Refunds within 30 days", ClaimType.policy)),
    )
    result = claims.extract_claims("Refunds are available within 30 days.")
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.claim_id == "C1"
    assert claim.sentence_id == "S1"
    assert claim.claim_type == ClaimType.policy


def test_multiple_claims_including_two_from_one_sentence(monkeypatch):
    monkeypatch.setattr(
        claims,
        "ask_llm_json",
        fake_llm(
            ("S1", "Refunds within 30 days", ClaimType.policy),
            ("S1", "Customized products are excluded", ClaimType.policy),
            ("S2", "Maximum reimbursement is ₹50,000", ClaimType.financial),
        ),
    )
    result = claims.extract_claims("Refunds in 30 days except custom items. Max is ₹50,000.")
    assert [c.claim_id for c in result.claims] == ["C1", "C2", "C3"]
    assert [c.sentence_id for c in result.claims] == ["S1", "S1", "S2"]


def test_sentence_with_no_claim(monkeypatch):
    monkeypatch.setattr(claims, "ask_llm_json", fake_llm())
    result = claims.extract_claims("Have a nice day.")
    assert len(result.sentences) == 1
    assert result.claims == []


def test_every_claim_points_to_an_existing_sentence(monkeypatch):
    monkeypatch.setattr(
        claims,
        "ask_llm_json",
        fake_llm(("S1", "a", ClaimType.general), ("S2", "b", ClaimType.date)),
    )
    result = claims.extract_claims("One. Two.")
    ids = {s.sentence_id for s in result.sentences}
    assert all(c.sentence_id in ids for c in result.claims)


def test_unknown_sentence_id_is_rejected_after_one_retry(monkeypatch):
    calls = []

    def bad(prompt, schema):
        calls.append(1)
        return fake_llm(("S99", "made up", ClaimType.general))(prompt, schema)

    monkeypatch.setattr(claims, "ask_llm_json", bad)
    with pytest.raises(LLMError, match="unknown sentence id"):
        claims.extract_claims("Only sentence.")
    assert len(calls) == 2  # first try + exactly one retry


def test_invalid_llm_response_retries_once_then_succeeds(monkeypatch):
    good = fake_llm(("S1", "ok", ClaimType.general))
    calls = []

    def flaky(prompt, schema):
        calls.append(1)
        if len(calls) == 1:
            raise LLMError("Gemini answered, but not in the expected JSON format.")
        return good(prompt, schema)

    monkeypatch.setattr(claims, "ask_llm_json", flaky)
    assert len(claims.extract_claims("Only sentence.").claims) == 1


def test_invalid_llm_response_fails_clearly_never_fake_claims(monkeypatch):
    def always_bad(prompt, schema):
        raise LLMError("Gemini answered, but not in the expected JSON format.")

    monkeypatch.setattr(claims, "ask_llm_json", always_bad)
    with pytest.raises(LLMError):
        claims.extract_claims("Only sentence.")


def test_prompt_contains_python_sentence_ids():
    prompt = claims._build_prompt(claims.split_sentences("Alpha. Beta."))
    assert "S1: Alpha." in prompt and "S2: Beta." in prompt


# ---------- API endpoint ----------

def test_endpoint_returns_sentences_and_claims(monkeypatch):
    monkeypatch.setattr(
        claims, "ask_llm_json", fake_llm(("S2", "Max is ₹50,000", ClaimType.financial))
    )
    response = TestClient(app).post(
        "/claims/extract", json={"document_text": "Hello there. Max is ₹50,000."}
    )
    body = response.json()
    assert response.status_code == 200
    assert [s["sentence_id"] for s in body["sentences"]] == ["S1", "S2"]
    assert body["claims"] == [
        {
            "claim_id": "C1",
            "sentence_id": "S2",
            "claim_text": "Max is ₹50,000",
            "claim_type": "financial",
        }
    ]


def test_endpoint_empty_document():
    response = TestClient(app).post("/claims/extract", json={"document_text": ""})
    assert response.status_code == 200
    assert response.json() == {"sentences": [], "claims": []}


def test_endpoint_llm_failure_is_502(monkeypatch):
    def fail(prompt, schema):
        raise LLMError("Gemini rate limit reached.")

    monkeypatch.setattr(claims, "ask_llm_json", fail)
    response = TestClient(app).post("/claims/extract", json={"document_text": "Something."})
    assert response.status_code == 502
    assert "rate limit" in response.json()["detail"]
