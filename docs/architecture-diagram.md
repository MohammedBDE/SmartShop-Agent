# Architecture Diagram — Smart Shop Assistant

Diagram of this implementation, following the request flow:
`USER QUERY → AGENT ROUTER → RAG / TOOLS → LLM → RESPONSE`.

## 1. Three-tier overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  CLIENT TIER  —  plain HTML + CSS + JavaScript (no framework)         │
│  client/index.html · client/style.css · client/app.js                 │
│                                                                       │
│   chat input · send button · scrollable history · route badge         │
│   trace rail · similarity meters · tool inspector · health pill       │
└───────────────┬──────────────────────────────────────────────────────┘
                │  fetch() — JSON over REST
                │  POST /chat   GET /history   GET /health
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  SERVER TIER  —  Flask (sole owner of all AI logic and secrets)       │
│  server/app.py + routes/ + services/                                  │
│                                                                       │
│   ┌─────────────┐   ┌──────────┐   ┌───────────┐   ┌──────────────┐   │
│   │ AGENT       │──▶│ RAG      │   │ TOOLS     │   │ LLM MODULE   │   │
│   │ ROUTER      │   │ MODULE   │   │ MODULE    │   │ LangChain    │   │
│   │ router.py   │   │ rag.py   │   │ tools.py  │   │ LCEL chain   │   │
│   │ LLM + rules │   │ pgvector │   │ 2 tools   │   │ llm_chain.py │   │
│   └─────────────┘   └──────────┘   └───────────┘   └──────────────┘   │
│                              ▼                                        │
│                      ┌───────────────────┐                            │
│                      │ RESPONSE FORMATTER│  formatter.py              │
│                      └───────────────────┘                            │
└───────────────┬──────────────────────────────────────────────────────┘
                │  psycopg2 (connection pool)
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  DATABASE TIER  —  PostgreSQL 16 + pgvector, in Docker                │
│  docker-compose.yml · server/db/schema.sql                            │
│                                                                       │
│   products · product_variants · discount_codes                        │
│   sessions · messages          (conversation history + memory)        │
│   tool_calls                   (tool audit log)                       │
│   kb_documents · kb_chunks     (vector store, VECTOR(384), HNSW)      │
└──────────────────────────────────────────────────────────────────────┘
```

The Anthropic API sits outside all three tiers and is reached over HTTPS by the **server
tier only** — the router calls it to classify, the LLM module calls it to extract tool
arguments and to write the final answer. Neither the client nor the database ever talks
to it.

## 2. Request flow (POST /chat)

```mermaid
flowchart TD
    A[Client: user types a question] -->|POST /chat JSON| B[Flask route chat.py]
    B --> C{Valid JSON?<br/>non-empty message?}
    C -->|no| C1[400 structured error] --> Z
    C -->|yes| D[ensure_session + save user message]
    D --> E[Load last N messages<br/>conversational memory]
    E --> F[AGENT ROUTER router.py]

    F --> F1{LLM classifier<br/>available?}
    F1 -->|yes| F2[Claude Haiku returns JSON<br/>route / tool_name / reasoning]
    F1 -->|no or invalid| F3[Rule-based fallback<br/>keyword patterns]
    F2 --> G{route}
    F3 --> G

    G -->|rag| H[RAG MODULE rag.py<br/>embed query - 384 dims<br/>pgvector cosine search<br/>return chunks + similarity]
    G -->|tool| I[TOOLS MODULE tools.py<br/>Claude picks arguments<br/>via Anthropic tool schema]
    G -->|direct| J[No external context]

    I --> I1[Execute tool against DB]
    I1 --> I2[(log to tool_calls)]

    H --> K[LLM MODULE llm_chain.py<br/>LCEL: prompt - ChatAnthropic - parser<br/>with_retry + with_fallbacks]
    I2 --> K
    J --> K

    K --> L[RESPONSE FORMATTER formatter.py<br/>answer + sources + route + router reasoning]
    L --> M[(save assistant message<br/>with route + sources)]
    M --> Z[JSON response to client]
    Z --> N[Client renders bubble + route badge]
```

## 3. Router decision table

| Customer asks | Route | Component used |
|---|---|---|
| "What is your return policy?" | `rag` | kb_chunks vector search |
| "Do you have the Classic Cotton T-Shirt in size L?" | `tool` | `check_product_availability` |
| "Total for 2 t-shirts with code WELCOME10?" | `tool` | `calculate_order_total` |
| "Hi, what can you help me with?" | `direct` | LLM only |

## 4. Data written on every request

| Table | Written by | Content |
|---|---|---|
| `sessions` | `chat.py` | one row per conversation |
| `messages` | `chat.py` | user message, then assistant message with `route`, `tool_name`, `router_reasoning`, `sources` |
| `tool_calls` | `tools.execute_tool` | tool name, input, output, status, latency |
