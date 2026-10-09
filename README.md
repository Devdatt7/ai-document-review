# ai-document-review
Evidence-driven review system for AI-genereted documents

## Setup

Requires Python 3.10+ and Node.js 18+.

```bash
# backend
python -m venv .venv
.venv\Scripts\activate          # Windows (Git Bash: source .venv/Scripts/activate)
pip install -r requirements.txt
cp .env.example .env            # then fill in your LLM key

# frontend
cd frontend
npm install
```

## Run

```bash
# backend (from repo root) -> http://localhost:8000/health
cd backend
uvicorn main:app --reload

# frontend (from repo root) -> http://localhost:5173
cd frontend
npm run dev
```

## Offline demonstration

The frontend provides good-document and flawed-document sample reports. They are clearly marked
as sample reports and do not call the backend or Gemini. Editing either input clears the loaded
sample report; **Analyze document** remains the separate live-analysis workflow. The presets and
refund policy source are synthetic demonstration text.

## Gemini usage limits

The free-tier limit is set by Google for the selected model and plan; the app cannot increase it.
An analysis uses one Gemini request to extract claims, then may use another request for each
evidence-backed claim that the local numeric/date checks cannot decide. Claims with no evidence
and numeric/date contradictions skip that second step. Malformed model output is retried once,
but quota errors are not retried because that would spend more requests without restoring quota.
If a quota error appears, check usage and reset timing in Google AI Studio, or choose a model/plan
with limits that fit your usage.

## Test

```bash
pytest tests
```

## Layout

- `backend/`: FastAPI app, one small module per pipeline step
- `frontend/`: React + Vite UI
- `data/sources/`: trusted source documents; `data/samples/`: demo AI documents
- `tests/`: pytest
