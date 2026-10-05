-- Smart Shop Assistant - schema definition (SQL migration)
-- Executed automatically on first creation of the PostgreSQL container.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------
-- Catalog
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id          SERIAL PRIMARY KEY,
    name        TEXT           NOT NULL,
    category    TEXT,
    price       NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    currency    TEXT           NOT NULL DEFAULT 'ILS',
    description TEXT,
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_name_lower ON products (lower(name));

CREATE TABLE IF NOT EXISTS product_variants (
    id             SERIAL PRIMARY KEY,
    product_id     INTEGER NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    size           TEXT    NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    sku            TEXT UNIQUE,
    UNIQUE (product_id, size)
);

CREATE INDEX IF NOT EXISTS idx_variants_product ON product_variants (product_id);

-- ---------------------------------------------------------
-- Conversations
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id               BIGSERIAL PRIMARY KEY,
    session_id       UUID NOT NULL REFERENCES sessions (session_id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content          TEXT NOT NULL,
    route            TEXT CHECK (route IN ('rag', 'tool', 'direct')),
    tool_name        TEXT,
    router_reasoning TEXT,
    sources          JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_session_time
    ON messages (session_id, created_at);

-- ---------------------------------------------------------
-- Tool-call audit log
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS tool_calls (
    id            BIGSERIAL PRIMARY KEY,
    session_id    UUID   REFERENCES sessions (session_id) ON DELETE CASCADE,
    message_id    BIGINT REFERENCES messages (id) ON DELETE SET NULL,
    tool_name     TEXT   NOT NULL,
    tool_input    JSONB  NOT NULL,
    tool_output   JSONB,
    status        TEXT   NOT NULL CHECK (status IN ('success', 'error')),
    error_message TEXT,
    latency_ms    INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls (session_id, created_at);

-- ---------------------------------------------------------
-- Knowledge base and vector store
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS kb_documents (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('policy', 'faq', 'catalog')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id          SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES kb_documents (id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content     TEXT    NOT NULL,
    embedding   VECTOR(384),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding
    ON kb_chunks USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------
-- Discount codes
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS discount_codes (
    code            TEXT PRIMARY KEY,
    percent_off     NUMERIC(5, 2)  CHECK (percent_off > 0 AND percent_off <= 100),
    amount_off      NUMERIC(10, 2) CHECK (amount_off > 0),
    min_order_total NUMERIC(10, 2) NOT NULL DEFAULT 0,
    active          BOOLEAN        NOT NULL DEFAULT TRUE,
    expires_at      TIMESTAMPTZ,
    CONSTRAINT one_discount_kind
        CHECK ((percent_off IS NOT NULL) <> (amount_off IS NOT NULL))
);
