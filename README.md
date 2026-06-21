
# Multi-Agent Eval Platform

**Production-grade multi-agent AI platform with eval framework, full observability, and safe tool gateway with human-in-the-loop approval.**

Built by [Datawebify](https://datawebify.com) · Live at [evals.datawebify.com](https://evals.datawebify.com) · [API Docs](https://evals.datawebify.com/docs)

---

## What This Is

Most multi-agent demos stop at "it works." This platform goes three steps further:

| Capability | What it does |
|---|---|
| **Eval Framework** | Offline + production eval runner with regression testing across prompt and model versions |
| **Full Observability** | Per-step trace capture (prompt, response, tool call, latency, cost) with a replay UI |
| **Safe Tool Gateway** | Schema-validated tool execution with human-in-the-loop approval for HIGH risk actions |

The domain is a customer support and billing assistant — a realistic, enterprise-relevant vehicle for demonstrating all three capabilities.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER / CLIENT                            │
│              (Next.js 14 Frontend — evals.datawebify.com)       │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP / WebSocket
┌────────────────────────▼────────────────────────────────────────┐
│                    FastAPI Backend                               │
│                  (Railway — Port 8000)                          │
│   /api/v1/chat  /api/v1/approvals  /api/v1/metrics              │
│   /api/v1/conversations  /api/v1/failures  /docs                │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│               LangGraph Orchestration Graph                      │
│                                                                 │
│   ┌──────────┐     ┌─────────────┐     ┌──────────────────┐    │
│   │  Router  │────▶│   Billing   │────▶│     Policy/      │    │
│   │  Agent   │     │   Agent     │     │   Grounding      │    │
│   └──────────┘     └─────────────┘     │     Agent        │    │
│        │                               └────────┬─────────┘    │
│        │                                        │              │
│        │           ┌─────────────┐     ┌────────▼─────────┐    │
│        └──────────▶│    Tool     │────▶│    Response      │    │
│                    │  Executor   │     │     Agent        │    │
│                    │   Agent     │     └────────┬─────────┘    │
│                    └──────┬──────┘              │              │
│                           │              ┌──────▼──────┐       │
│                           │              │ Eval/Safety │       │
│                           │              │   Agent     │       │
│                           │              └─────────────┘       │
└───────────────────────────┼─────────────────────────────────────┘
                            │
         ┌──────────────────▼──────────────────┐
         │          Tool Gateway                │
         │                                     │
         │  LOW risk  ──▶  Auto-execute        │
         │  HIGH risk ──▶  Redis Queue         │
         │                      │              │
         │               Human Approval        │
         │               (Frontend UI)         │
         └─────────────────────────────────────┘
                            │
         ┌──────────────────▼──────────────────┐
         │           Data Layer                 │
         │                                     │
         │  Supabase (PostgreSQL)              │
         │  ├── evals_conversations            │
         │  ├── evals_trace_steps              │
         │  ├── evals_eval_results             │
         │  ├── evals_tool_calls               │
         │  └── evals_approval_queue           │
         │                                     │
         │  Pinecone Vector DB                 │
         │  └── agai31-policy-kb               │
         │                                     │
         │  Redis                              │
         │  └── HIL approval queue             │
         └─────────────────────────────────────┘
```

---

## Agent Roles

| Agent | Role |
|---|---|
| **Router Agent** | Classifies intent: `billing_query`, `refund_request`, `policy_check`, `escalation`, `general` |
| **Billing Agent** | Calls `get_customer_profile`, `get_invoice_history` via Tool Gateway |
| **Policy/Grounding Agent** | RAG query to Pinecone, returns grounded excerpts with source citations |
| **Tool Executor Agent** | Executes `create_refund_ticket`, `escalate_to_human` after HIL approval |
| **Response Agent** | Synthesizes grounded final response from billing + policy context |
| **Eval/Safety Agent** | Scores every turn on 5 dimensions, flags low-confidence outputs |

---

## Tool Gateway

Every tool call passes through the gateway before execution:

```
Tool Call Request
      │
      ▼
Schema Validation (Pydantic)
      │
      ▼
Risk Classification
      │
   ┌──┴──┐
  LOW   HIGH
   │     │
   ▼     ▼
Auto  Redis Queue ──▶ Human Approval UI
Execute              Approve ──▶ Execute
                     Reject  ──▶ Refusal to Agent
```

**LOW risk tools** (auto-execute): `get_customer_profile`, `get_invoice_history`, `check_refund_policy`

**HIGH risk tools** (HIL approval): `create_refund_ticket`, `escalate_to_human`

---

## Eval Framework

### Offline Eval
```bash
cd backend
python -m app.eval.eval_runner --mode offline --prompt-version v1 --model-version gpt-4o
```

Runs all 25 test cases across 5 categories and prints a summary table:
```
============================================================
  EVAL REPORT — v1 / gpt-4o
============================================================
  Total Cases   : 25
  Passed (>=60%): 20
  Failed (<60%) : 5
  Task Success Rate   : 72.0%
  Grounding Accuracy  : 81.0%
  Tool Correctness    : 68.0%
  Policy Compliance   : 90.0%
  Escalation Correct  : 85.0%
  Avg Latency         : 4800 ms
  Avg Token Cost      : $0.00850
============================================================
```

### Regression Testing
```bash
python -m app.eval.eval_runner \
  --mode regression \
  --baseline eval_data/reports/eval_report_<id>_v1_gpt-4o.json \
  --prompt-version v2 \
  --model-version gpt-4o
```

### Production Trace Eval
```bash
python -m app.eval.eval_runner \
  --mode trace \
  --conversation-id <conversation_id>
```

---

## Local Setup

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker + Docker Compose
- Redis (via Docker)
- Supabase account
- Pinecone account
- OpenAI API key

### 1. Clone the repo
```bash
git clone https://github.com/umair801/multi-agent-eval-platform.git
cd multi-agent-eval-platform
```

### 2. Configure environment
```bash
cp backend/.env.example backend/.env
```

Fill in `backend/.env`:
```env
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
PINECONE_API_KEY=your_key
PINECONE_INDEX_NAME=agai31-policy-kb
SUPABASE_URL=your_url
SUPABASE_KEY=your_key
REDIS_URL=redis://localhost:6379/0
PRIMARY_MODEL=gpt-4o
FALLBACK_MODEL=claude-sonnet-4-6
```

Create `frontend/.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Set up the database
Run `database/schema.sql` in your Supabase SQL editor.

### 4. Ingest policy documents
```bash
cd backend
pip install -r requirements.txt
python -c "from app.rag.ingestor import ingest_documents; print(ingest_documents())"
```

### 5. Start with Docker Compose
```bash
docker-compose up --build
```

Or run services individually:
```bash
# Terminal 1 — Backend
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

### 6. Access the platform
| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

---

## Demo Walkthrough

### 1. Basic policy query
Go to Chat → send: `What is your refund policy?`

Watch the server logs to see: Router → Policy Agent (Pinecone RAG) → Response Agent → Eval Safety Agent

### 2. Billing query with tool call
Send: `What is my current account status and latest invoice?`

This triggers: Router → Billing Agent → `get_customer_profile` (LOW risk, auto-executes) → Response

### 3. Refund request with HIL approval
Send: `I was charged twice in January. I need a refund.`

Then go to **Approvals** tab — a `create_refund_ticket` card appears.
Click **Approve** to execute, or **Reject** to send a refusal back.

### 4. Inspect the trace
Go to **Traces** → click any conversation → expand each step to see:
- Full prompt sent to the model
- Model response
- Tool inputs and outputs
- Latency and token cost per step

### 5. Replay a failed conversation
On any trace detail page, click **▶ Replay** to re-execute the original message end-to-end through the current agent graph.

### 6. Run the offline eval
```bash
cd backend
python -m app.eval.eval_runner --mode offline
```

### 7. Check platform metrics
Go to **Metrics** tab to see task success rate, latency, cost per turn, failure category breakdown, and system health summary.

---

## How to Replay a Failed Conversation

1. Go to **Traces** and filter by `outcome: failed`
2. Click the conversation to open the trace detail
3. Inspect which agent step failed (red error badge)
4. Click **▶ Replay** to re-run with the current prompt and model
5. Compare the new trace against the original

Alternatively, via API:
```bash
curl -X POST http://localhost:8000/api/v1/conversations/<id>/replay
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (TypedDict state) |
| LLM Primary | GPT-4o |
| LLM Fallback | Claude API (claude-sonnet-4-6) |
| Embeddings | OpenAI text-embedding-3-small |
| Vector DB | Pinecone |
| Backend | FastAPI + Python 3.12 |
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| Database | Supabase (PostgreSQL) |
| Task Queue | Redis (human approval queue) |
| Deployment | Docker Compose (local) + Railway (production) |

---

## Project Structure

```
multi-agent-eval-platform/
├── backend/
│   ├── app/
│   │   ├── agents/          # 6 LangGraph agent nodes
│   │   ├── eval/            # Offline + regression eval runner
│   │   ├── gateway/         # Tool Gateway with HIL queue
│   │   ├── observability/   # Trace writer to Supabase
│   │   ├── rag/             # Pinecone RAG pipeline
│   │   ├── schemas/         # Pydantic models + AgentState
│   │   └── tools/           # LLM factory (GPT-4o + Claude fallback)
│   ├── main.py              # FastAPI app + all endpoints
│   └── requirements.txt
├── frontend/
│   └── app/
│       ├── page.tsx          # Chat interface
│       ├── traces/           # Conversation list + step drill-down
│       ├── approvals/        # HIL approval queue dashboard
│       └── metrics/          # Failure dashboard + KPI metrics
├── eval_data/
│   ├── test_cases.json       # 25 curated eval test cases
│   ├── policy_docs/          # Source documents for RAG
│   └── reports/              # Generated eval reports
├── database/
│   └── schema.sql            # Supabase table definitions
├── docker-compose.yml
└── README.md
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/chat` | Submit message, run full agent pipeline |
| GET | `/api/v1/conversations` | List all conversations |
| GET | `/api/v1/conversations/{id}/trace` | Get full trace for a conversation |
| POST | `/api/v1/conversations/{id}/replay` | Replay a saved conversation |
| GET | `/api/v1/approvals` | List pending HIL approvals |
| POST | `/api/v1/approvals/{id}/approve` | Approve a HIGH risk tool call |
| POST | `/api/v1/approvals/{id}/reject` | Reject a HIGH risk tool call |
| GET | `/api/v1/metrics` | Platform-wide performance metrics |
| GET | `/api/v1/failures` | Failure category breakdown |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger API documentation |

---

## Built By

**Muhammad Umair** — Agentic AI Specialist  
[Datawebify](https://datawebify.com) · [GitHub](https://github.com/umair801) · [Upwork](https://upwork.com/freelancers/umair801)
```