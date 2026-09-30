# Adversarial Arena Backend

Research-grade LLM jailbreak attack-defense experimentation platform. Designed for automated red-teaming, defense evaluation, and Attack Success Rate (ASR) benchmarking across proprietary and open-weights models.

---

## Architecture Overview

```
                      +-----------------------------------+
                      |         FastAPI Gateway           |
                      |  (Auth, JWKS, Rate Limit, CORS)   |
                      +-----------------+-----------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
        [ REST / SSE API ]                             [ Celery Queue ]
                 |                                             |
        +--------+--------+                           +--------+--------+
        |  PostgreSQL 16  |                           |  Celery Worker  |
        |  (Runs, Models, |                           |  (LangGraph     |
        |   Defenses, DB) |                           |   Orchestrator) |
        +-----------------+                           +--------+--------+
                 ^                                             |
                 |                                    +--------+--------+
        [ Redis 7 Cache ]                             | LiteLLM / Target|
        (JWKS, RateLimit)                             | (OpenAI, Ollama)|
                                                      +-----------------+
```

### Key Components

- **FastAPI (ASGI)**: High-performance asynchronous API endpoints under `/api/v1/`.
- **SQLAlchemy 2.0 (Async) + Alembic**: Type-safe async ORM over PostgreSQL with connection pooling.
- **LangGraph Orchestrator**: Dynamic state-machine orchestrating attack mutation, defense filtering, model inference, and jailbreak evaluation.
- **Pluggable Attacks**: Abstracted attack engine supporting PAIR (Prompt Automatic Iterative Refinement), multi-turn progressive crescendo, AutoDAN genetic algorithms, and GCG.
- **Pluggable Defenses**: Modular defense pipeline supporting keyword/regex filters, LLM Guard Judges, and Chain-of-Thought defensive wrappers.
- **Celery + Redis**: Distributed task execution for long-running attack suites with Redis pub/sub real-time SSE progress streaming.
- **Security & Cryptography**: Fernet encryption for API keys at rest, Clerk JWKS token verification with Redis caching, and Svix signature validation for webhooks.

---

## Quickstart (Docker)

### 1. Prerequisites
- Docker Engine 24+ & Docker Compose v2+
- Python 3.12+ (for local development/testing)

### 2. Configure Environment
Copy the sample environment file:
```bash
cp .env.example .env
```
Generate an encryption key:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Update `ENCRYPTION_KEY` in `.env`.

### 3. Launch Services
```bash
make up
```
This starts:
- `postgres` (Port 5432)
- `redis` (Port 6379)
- `api` (Port 8000)
- `worker` (Celery background worker)
- `ollama` (Port 11434)
- `mailhog` (Port 8025 Web UI / 1025 SMTP)

### 4. Run Migrations & Seed Data
```bash
make migrate
make seed
```

### 5. Access the API
- Interactive OpenAPI Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- Readiness Check: [http://localhost:8000/api/v1/ready](http://localhost:8000/api/v1/ready)
- Metrics: [http://localhost:8000/metrics](http://localhost:8000/metrics)

---

## Development & Testing

```bash
# Run unit and integration tests
make test

# Code quality check
make lint

# Auto-format
make format
```

---

## API Summary (`/api/v1`)

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/auth/me` | GET | Current authenticated user profile |
| `/attacks` | GET, POST | List & create attack templates |
| `/attacks/{id}` | GET, PATCH, DELETE | Attack template lifecycle |
| `/attacks/registry` | GET | List registered attack algorithms and schemas |
| `/models` | GET, POST | Manage target model configurations |
| `/models/{id}/test` | POST | Verify model connectivity and inference |
| `/defenses` | GET, POST | Manage defense rules |
| `/runs` | POST | Submit new attack-defense test run (202 Accepted) |
| `/runs` | GET | List historical runs with filters |
| `/runs/{id}` | GET, DELETE | Run details and cleanup |
| `/runs/{id}/results`| GET | Paginated prompt-level results |
| `/runs/{id}/stream` | GET | Server-Sent Events (SSE) live progress stream |
| `/runs/{id}/abort`  | POST | Terminate active running evaluation |
| `/reports/{id}`     | GET | Comprehensive JSON benchmark report |
| `/reports/{id}/pdf` | GET | Download styled PDF evaluation report |
| `/reports/compare`  | GET | Head-to-head comparison between two runs |
| `/webhooks/clerk`   | POST | Svix-verified webhook for user synchronization |
