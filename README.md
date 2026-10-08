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

## Test

```bash
pytest tests
```

## Layout

- `backend/`: FastAPI app, one small module per pipeline step
- `frontend/`: React + Vite UI
- `data/sources/`: trusted source documents; `data/samples/`: demo AI documents
- `tests/`: pytest
