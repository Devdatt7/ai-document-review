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

## Deploy backend on Render

Create a Render Blueprint from this repository to use `render.yaml`, and provide
`GEMINI_API_KEY` when prompted. Do not commit your API key.

For an existing Render web service, update its settings manually (adding the
Blueprint file does not update a manually configured service):

- Runtime: **Python**
- Root Directory: leave empty (repository root)
- Build Command: `pip install -r requirements.txt`
- Start Command: `python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`
- Environment: set `GEMINI_API_KEY` to your key; optional provider/model settings
  are listed in `.env.example`.

Save the settings and redeploy. Visit `https://<your-service>.onrender.com/health`;
the response should be `{"status":"ok"}`.

This backend is a FastAPI ASGI application in `backend/main.py`, not a Django WSGI
application. Do not use the frontend's Vercel URL or `app.wsgi:application` as the
server entry point. Uvicorn is already included in `requirements.txt`, so Gunicorn
is not required.

## Connect the Vercel frontend

Production frontend builds default to `https://ai-document-review-1.onrender.com`;
local development still uses `http://localhost:8000`. To override the backend,
set `VITE_API_URL` in Vercel's environment settings, then redeploy the frontend
(Vite embeds this value at build time). Remove any old localhost value.

The backend allows `https://ai-document-review-two-blond.vercel.app` and local
development origins. For another frontend domain, set `CORS_ORIGINS` on Render
to a comma-separated list of exact allowed origins, then redeploy the backend.
Origins must not contain paths, trailing slashes, or `#/app`. Do not allow every
Vercel domain. Redeploy both services after these connection changes.

## Offline demonstration

The frontend provides good-document and flawed-document sample reports. They are clearly marked
as sample reports and do not call the backend or Gemini. Editing either input clears the loaded
sample report; **Analyze document** remains the separate live-analysis workflow. The presets and
refund policy source are synthetic demonstration text.

## Gemini usage limits

The free-tier limit is set by Google for the selected model and plan; the app cannot increase it.
An analysis uses one Gemini request to extract claims, then batches up to four evidence-backed
claims per verification request when local numeric/date checks cannot decide them. Claims with no
evidence and numeric/date contradictions skip verification. A malformed response may receive one
format-repair request per batch; quota/rate-limit errors are not retried. If a quota error appears,
check usage and reset timing in Google AI Studio.

## Test

```bash
pytest tests
```

## Layout

- `backend/`: FastAPI app, one small module per pipeline step
- `frontend/`: React + Vite UI
- `data/sources/`: trusted source documents; `data/samples/`: demo AI documents
- `tests/`: pytest
