# NeuroFence

AI Agent Safety System - real-time contamination detection & automatic isolation.

## What you need to provide (keys / credentials)

- Required: nothing if you use Docker Compose defaults.
- Required (if using your own Postgres): `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (or `DATABASE_URL`).
- Optional: `OPENAI_API_KEY` (only for future OpenAI-based extensions; current system works offline).

Security note: never put real keys in `.env.example`. Use a local `.env` file (gitignored).

Details: see docs/SECRETS.md.

## Quick start (Windows)

### Prerequisites
- Python 3.9+
- PostgreSQL 13+ (recommended for persistence)

### Option A (recommended): Run everything with Docker

1) Install Docker Desktop
- Download: https://www.docker.com/products/docker-desktop/
- Ensure WSL2 is enabled (Docker Desktop installer will guide you).

2) Start NeuroFence (API + Postgres)

One-command launcher (Windows):

```powershell
cd c:\Users\Win11\Desktop\NeuroFence
./run-neurofence.cmd
```

This will:
- build + start the Docker Compose stack
- wait for `GET /health` to return `{"status":"healthy"}`
- run `pytest -q` inside the API container

Alternatively, run Compose directly:

```powershell
cd c:\Users\Win11\Desktop\NeuroFence
docker compose up --build
```

3) Open the API
- Health: http://localhost:8000/health

Notes:
- DB is persisted in a Docker volume `neurofence_pgdata`.
- Schema is created automatically on API startup.

### Option B: Local Python + your local PostgreSQL

### 1) Create venv + install deps

```powershell
cd c:\Users\Win11\Desktop\NeuroFence
py -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Configure environment

```powershell
copy .env.example .env
# edit .env if your Postgres creds differ
```

### 3) Initialize DB

```powershell
python init_db.py
```

### 4) Run API

```powershell
python -m uvicorn backend.main:app --reload --port 8000
```

Health check:
- http://localhost:8000/health

### 5) Run demo

```powershell
python examples\demo_complete.py
```

## API endpoints
- `GET /health`
- `POST /intercept`
- `GET /stats`
- `GET /forensics/{agent_name}`
- `POST /isolate/{agent_name}`
- `POST /release/{agent_name}`
- `POST /update-baseline/{agent_name}`

Example request:

```bash
curl -X POST http://localhost:8000/intercept \
  -H "Content-Type: application/json" \
  -d '{"sender":"agent_a","recipient":"agent_b","content":"hello"}'
```

## Testing

The pytest suite uses an in-memory SQLite database and a fake embedding model (so it runs fast and does not download large ML models):

```powershell
pytest -q
```

## Framework integration (automatic interception)

For a full, step-by-step integration guide (recommended), see: `docs/INTEGRATION.md`.

### Install the SDK (like a framework)

If you want to integrate NeuroFence into another Python project, install the SDK package:

```powershell
cd C:\path\to\NeuroFence
pip install -e .
```

NeuroFence can run as a standalone service and **enforce interception** as long as you integrate at an enforcement point.

Two universal patterns:

1) **Message-bus / send() wrapper (most reliable)**
  - If your framework has any function/method that ultimately sends agent-to-agent messages, wrap it once.
  - Every message is checked via `POST /intercept` before delivery.

2) **LLM gateway (works across frameworks that all call the same LLM API)**
  - Point your framework's LLM base URL at a gateway that calls NeuroFence before forwarding.
  - This protects messages that flow through the model call path, but it does *not* automatically cover out-of-band channels.

### Drop-in send() wrapper (Python)

See [examples/framework_agnostic_integration.py](examples/framework_agnostic_integration.py) for a minimal example.

The wrapper lives in [neurofence_sdk/guard.py](neurofence_sdk/guard.py):

```python
from neurofence_sdk import wrap_send

def send_message(sender, recipient, content):
   ...

send_message = wrap_send(send_message, base_url="http://localhost:8000")
```

## Notes
- For production, keep `ISOLATION_ENABLED=true` and use PostgreSQL.
- Baselines improve semantic anomaly detection; update per agent via `POST /update-baseline/{agent_name}`.
