# TB Isolation Chatbot

The existing React frontend is retained. Its chat requests continue to use `POST /api/chat` and stream plain text. The Express backend now routes general TB questions to Qdrant RAG and case-specific isolation questions through structured extraction, Python schema validation, the deterministic Python rule engine, and evidence review.

> **Clinical safety:** the rules in `tb_isolation_rules_package/` identify themselves as a draft, not clinically validated policy. Their results are reproducible, not clinically certain. Do not use them to make patient-care decisions without review and approval by qualified TB clinicians and public-health authorities. The engine does not grant healthcare or congregate-facility clearance.

## Prerequisites

- Node.js 20.16 or newer and npm
- Python 3.10 or newer
- Docker Desktop with Docker Compose, or a reachable Qdrant Cloud collection
- An OpenAI API key for task classification, case extraction, and answer generation
- The Python packages in `backend/requirements.txt` for local embeddings and PDF ingestion

The Qdrant collection must use the same local embedding model and vector dimension as document ingestion. The default is `intfloat/e5-large-v2`, 1024 dimensions. A local `.venv` is detected automatically; otherwise set `PYTHON_EXECUTABLE` in the environment or ensure `python` is on `PATH`.

## Configure and start Qdrant

At the repository root, copy the environment template if needed:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Set `OPENAI_API_KEY` and `QDRANT_URL` in `.env`. For local development, use:

```env
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_MODEL=intfloat/e5-large-v2
EMBEDDING_DIMENSION=1024
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=tb_guidance
NODE_KNOWLEDGE_DIR=knowledge-base
PORT=3001
```

Start local Qdrant:

```powershell
docker compose up -d
```

The Qdrant data is stored in a named Docker volume. Cloud deployments should set the Qdrant URL and API key in the server environment; never put the key in frontend code.

## Install dependencies and index guidance

Install Node and Python packages:

```powershell
npm install
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

The repository includes source PDFs in `documents/`. Index them with the existing Python PDF pipeline, which uses the same E5 embeddings as query-time retrieval:

```powershell
.\.venv\Scripts\python.exe backend\ingest.py documents
```

This PDF pipeline may use the configured OpenAI vision model when `ENABLE_VISION=true`; review its settings and costs before ingestion. For additional `.pdf`, `.md`, or `.txt` documents in `knowledge-base/` (the `NODE_KNOWLEDGE_DIR` default), the Node ingestion command uses the same local embedding worker:

```powershell
npm run ingest
```

Changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSION` requires re-indexing with that same model and dimension. The backend checks the Qdrant collection dimension and will fail startup on a mismatch rather than search with incompatible vectors.

## Run the application

Open two terminals at the repository root.

Terminal 1 — backend:

```powershell
npm start
```

At startup the API validates Qdrant and loads the local embedding model. Terminal 2 — unchanged React frontend:

```powershell
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`). The API listens on `http://localhost:3001`.

## Backend request flow

The current frontend request shape is preserved: `message`, `patientContext`, `structuredData`, and `conversationHistory`.

1. The model classifies a turn as a case-specific isolation decision or a general guidance question.
2. General questions follow the existing bounded RAG flow.
3. For an isolation decision, the model extracts only user-provided facts into `tb_isolation_rules_package/input_schema.json`. Current form selections are preserved as explicit values.
4. The case is validated and normalized by the Python rule package. Invalid fields produce an explicit service error; they are not converted into safe-looking defaults.
5. Before evaluation, the backend asks follow-up questions for required values that are missing or conflicting. A reply to a pending rule-engine clarification is automatically routed back through case extraction; the exact prior question and user's follow-up replies are provided so short or numbered answers can be mapped to the requested fields. If a value is explicitly unknown, that uncertainty is passed to the rules.
6. The Python engine produces the deterministic level, status, duration, blockers, and rule IDs. Only after that result exists does the backend retrieve Qdrant evidence. It may make one focused follow-up search if the evidence review finds a gap or conflict.
7. Decision-support replies use fixed `Decision`, `Why?`, `Known case facts`, `Unresolved criteria`, `Evidence`, and `Important` sections. The `Decision` section translates the Python engine's status into a direct statement such as continuing restrictions to its conditional target, maintaining a provisional hold, or eligibility to discontinue under draft policy. The rationale and action come only from the rule result; evidence status is reported separately with retrieved citations. No generative answer step can replace or compete with the rule result.

The backend currently invokes the Python rule bridge and uses a persistent local sentence-transformer worker. Patient context is supplied only for the active request; it is not added to the Qdrant knowledge collection.

In development, the backend writes `[tb-rag]` console traces for classification, extracted case fields, schema validation, deterministic rule results, RAG retrieval and evidence review, and the assembled response. Case details may contain sensitive health information; use synthetic cases for development and protect terminal output. These detailed traces are suppressed when `NODE_ENV=production` or `NODE_ENV=test`. The deterministic rule engine remains the sole source of case-specific isolation decisions; RAG only checks and reports supporting, insufficient, or conflicting evidence.

## Tests

Run the Node/RAG/API tests and the deterministic rule-engine suite:

```powershell
npm test
npm run build
```

The rule package can also be tested directly:

```powershell
python -m unittest discover -s tb_isolation_rules_package -p test_tb_isolation_rules.py
```

Before any clinical use, domain experts must validate the rule policy, extraction behavior, retrieval quality, citation accuracy, and evidence-conflict handling. Review privacy, access control, and logging before sending real patient information to any model or hosted service.
