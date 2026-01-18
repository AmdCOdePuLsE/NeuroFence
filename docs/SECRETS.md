# NeuroFence secrets/keys

NeuroFence runs fully offline by default (local embedding model) and does **not** require any API keys.

## Required values (only if using PostgreSQL)

If you use Postgres (recommended for persistence), you need credentials:

- `DB_HOST` / `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- Or a single `DATABASE_URL`

### How to get them

**Option A — Docker Compose (recommended):**
- You don't need to “get” credentials — compose sets them.
- Default values are:
  - user: `postgres`
  - password: `postgres`
  - db: `neurofence_hack`

**Option B — Existing local PostgreSQL:**
- Use the credentials you already configured in your Postgres install.
- If you need to create them:
  1. Open `psql` as an admin user.
  2. Create DB and user, then grant rights.

## Optional values

### `OPENAI_API_KEY` (optional)
Only needed if you later add an OpenAI-based detector or LLM integration.

How to get it:
1. Create an account on the OpenAI platform.
2. Go to the API keys page.
3. Create a new secret key.
4. Put it in `.env` as `OPENAI_API_KEY=...`.

Security:
- Never commit `.env` to git.
- Rotate keys if accidentally exposed.
