-- Lets Postgres store embeddings (lists of numbers) and search them by similarity
CREATE EXTENSION IF NOT EXISTS vector;

-- ============ USERS ============
-- People who log in (GitHub login comes in Phase 10)
CREATE TABLE users (
    id          BIGSERIAL PRIMARY KEY,
    github_id   BIGINT UNIQUE NOT NULL,
    username    TEXT NOT NULL,
    avatar_url  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============ REPOSITORY DATA (shared by all users) ============
-- One row per GitHub repo. A URL can only be indexed once.
CREATE TABLE repositories (
    id          BIGSERIAL PRIMARY KEY,
    url         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    commit_sha  TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    overview    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per source file, including its full text
CREATE TABLE files (
    id        BIGSERIAL PRIMARY KEY,
    repo_id   BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    path      TEXT NOT NULL,
    language  TEXT,
    content   TEXT NOT NULL,
    UNIQUE (repo_id, path)
);

-- One row per function / class / method. This is the unit we search over.
CREATE TABLE chunks (
    id              BIGSERIAL PRIMARY KEY,
    repo_id         BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_id         BIGINT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    name            TEXT NOT NULL,
    qualified_name  TEXT NOT NULL,
    start_line      INT NOT NULL,
    end_line        INT NOT NULL,
    signature       TEXT,
    docstring       TEXT,
    code            TEXT NOT NULL,
    embedding       vector(384),
    tsv             tsvector GENERATED ALWAYS AS (
                      to_tsvector('simple',
                        name || ' ' || qualified_name || ' ' ||
                        coalesce(docstring, '') || ' ' || code)
                    ) STORED
);

CREATE INDEX chunks_repo_idx      ON chunks (repo_id);
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_idx       ON chunks USING gin (tsv);

-- The call graph: "this chunk calls something named X"
CREATE TABLE symbol_edges (
    id         BIGSERIAL PRIMARY KEY,
    repo_id    BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    src_chunk  BIGINT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    dst_name   TEXT NOT NULL,
    dst_chunk  BIGINT REFERENCES chunks(id) ON DELETE SET NULL,
    kind       TEXT NOT NULL
);

CREATE INDEX edges_src_idx ON symbol_edges (src_chunk);
CREATE INDEX edges_dst_idx ON symbol_edges (dst_chunk);

-- ============ PER-USER DATA ============
-- Which user viewed which repo, and when (powers "My repositories")
CREATE TABLE user_repositories (
    user_id          BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repo_id          BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    first_viewed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_viewed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, repo_id)
);

CREATE INDEX user_repositories_user_idx ON user_repositories (user_id, last_viewed_at DESC);

-- One row per chat, like one entry in a chat sidebar
CREATE TABLE conversations (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repo_id     BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    title       TEXT NOT NULL DEFAULT 'New chat',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX conversations_user_idx ON conversations (user_id, updated_at DESC);

-- One row per message inside a chat
CREATE TABLE messages (
    id               BIGSERIAL PRIMARY KEY,
    conversation_id  BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    citations        JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX messages_conv_idx ON messages (conversation_id, created_at);