CREATE TABLE IF NOT EXISTS menu_items (
    menu_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    aliases TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL,
    single_price INTEGER NOT NULL CHECK (single_price >= 0),
    set_price INTEGER NOT NULL CHECK (set_price >= single_price),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id BIGSERIAL PRIMARY KEY,
    menu_id VARCHAR(20) REFERENCES menu_items(menu_id),
    document_type VARCHAR(30) NOT NULL,
    content TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    order_id BIGSERIAL PRIMARY KEY,
    order_number VARCHAR(20) UNIQUE,
    session_id VARCHAR(100) NOT NULL,
    execution_mode VARCHAR(20) NOT NULL CHECK (execution_mode IN ('workflow', 'agent')),
    total_price INTEGER NOT NULL CHECK (total_price >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    menu_id VARCHAR(20) NOT NULL REFERENCES menu_items(menu_id),
    menu_name VARCHAR(100) NOT NULL,
    order_option VARCHAR(20) NOT NULL CHECK (order_option IN ('single', 'set')),
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 20),
    unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
    line_total INTEGER NOT NULL CHECK (line_total = unit_price * quantity)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_menu_id
    ON knowledge_documents(menu_id);

CREATE INDEX IF NOT EXISTS idx_orders_session_id
    ON orders(session_id);
