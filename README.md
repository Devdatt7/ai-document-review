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
An analysis uses one Gemini request to extract claims, then batches up to twelve evidence-backed
claims per verification request when local numeric/date checks cannot decide them. Claims with no
evidence and numeric/date contradictions skip verification. A malformed response may receive one
format-repair request per batch; quota/rate-limit errors are not retried. If a quota error appears,
check usage and reset timing in Google AI Studio.

## OpenAI backup

To enable OpenAI, set `OPENAI_API_KEY` in the backend `.env` for local development,
or in Render's Environment settings for deployment. Optionally set `OPENAI_MODEL`
(default: `gpt-4o-mini`). Restart or redeploy the backend after changing settings.
The existing `httpx` dependency is used; no additional package is needed.

Requests try Gemini first, then OpenRouter free, xAI, OpenAI, and Claude if configured.
The next provider is used only when the preceding provider has no key or reaches
its rate/usage limit. Invalid credentials, timeouts, and other errors remain
visible instead of silently switching providers. OpenAI can also work alone
when Gemini and xAI keys are unset. Structured answers are validated against the
same Pydantic schemas as Gemini.

Enabling a backup permits sending the document and evidence to that provider.
OpenAI API usage may incur charges and requires an API account with available
quota/billing; a ChatGPT subscription does not supply API credits. Never add
`OPENAI_API_KEY` to Vercel frontend variables, browser code, or Git.

## Anthropic Claude backup

Set `ANTHROPIC_API_KEY` in the backend `.env` or Render Environment settings.
Optionally set `ANTHROPIC_MODEL` (default: `claude-haiku-4-5-20251001`), then restart
or redeploy the backend. No additional dependency is needed.

Claude is the final backup after configured Gemini, OpenRouter free, xAI, and OpenAI providers
reach their rate limits. Missing providers are skipped; non-quota errors remain
visible. With all other keys unset, Claude can work alone. Structured requests
use a forced result tool and the existing Pydantic validation; no external tool
is executed. Truncated answers are reported as errors rather than used as results.

Enabling this backup sends document/evidence text to Anthropic and may incur API
charges. Keep `ANTHROPIC_API_KEY` out of frontend variables, browser code, and Git.
An Anthropic API account with available quota is required; a Claude subscription
does not provide API credits. This does not change the Supabase sign-in setup.

## OpenRouter free backup

Set `OPENROUTER_API_KEY` in the backend `.env` or Render Environment settings
(create a key at https://openrouter.ai/settings/keys), then restart or redeploy.
`OPENROUTER_MODEL` defaults to `openrouter/free`, which routes to available free
models. You may select a specific model ID ending in `:free`; other model IDs
are rejected before a request is sent. No additional dependency is required.

The backend loads only the repository-root `.env`, regardless of the directory
from which it is started; existing environment variables take precedence.
`frontend/.env.local` does not configure the backend. Never place provider keys
in that frontend file. Local `.env` files are not uploaded to Render: configure
the deployed backend's variables directly in Render and redeploy the latest code.

OpenRouter runs after Gemini and before the paid backups. To use only free
providers, leave `XAI_API_KEY`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY` unset.
To use OpenRouter alone, also unset both `GEMINI_API_KEY` and `GEMINI_API_KEYS`.
Rate limits allow the next configured provider to run; other errors stay visible.
JSON requests require provider support for JSON mode and are validated using
the same Pydantic schemas. Incomplete or blocked results are rejected.

Free does not mean unlimited: availability and daily/minute limits vary.
Check current limits at https://openrouter.ai/docs/api/reference/limits.
Enabling the provider sends document/evidence text to OpenRouter and its selected
upstream provider; review their data policies and use synthetic documents.
Keep `OPENROUTER_API_KEY` out of Vercel frontend variables, browser code, and Git.

## Analysis time limits

Analysis extracts claims, then verifies eligible claims in sequential batches of
twelve, reducing verification round trips by up to three times compared with
four-claim batches. The same ID, citation, and exact-quote checks still apply.
Multiple slow calls and format-repair attempts can add up; free-model routing
also has variable latency. There is no guaranteed "few seconds" completion time.

The `/analyze` endpoint shares a 295-second budget across extraction,
verification, repairs, and provider fallbacks. Each outgoing request is limited
to the remaining budget or `LLM_TIMEOUT_SECONDS` (default: 60), whichever is
smaller. Gemini SDK retries are disabled because the app already handles fallback.
Expired budgets stop further calls and return HTTP 504, not a partial success.
HTTP timeouts depend on network phases, so this is not a hard process-kill deadline.

The browser aborts waiting after 300 seconds (5 minutes), including while reading the response,
clears the spinner, and shows a timeout error. Browser cancellation does not
guarantee immediate cancellation of an already-running backend request.
Try a shorter document or choose an available faster `:free` OpenRouter model.
This is a five-minute limit on browser waiting, not a minimum runtime or a guarantee
that a free AI provider will produce a complete report within five minutes.
Individual provider requests still default to a 60-second timeout; the longer
budget lets multiple extraction, verification, and repair calls complete.
Push these changes and redeploy both Render and Vercel to apply the limits.

## Test

```bash
pytest tests
```

## Layout

- `backend/`: FastAPI app, one small module per pipeline step
- `frontend/`: React + Vite UI
- `data/sources/`: trusted source documents; `data/samples/`: demo AI documents
- `tests/`: pytest
