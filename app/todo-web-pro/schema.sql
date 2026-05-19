PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT    NOT NULL UNIQUE COLLATE NOCASE
                        CHECK(length(username) BETWEEN 3 AND 32),
  password_hash TEXT    NOT NULL CHECK(length(password_hash) = 60),
  display_name  TEXT    NOT NULL DEFAULT '' CHECK(length(display_name) <= 80),
  created_at_ms INTEGER NOT NULL,
  last_login_ms INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS users_username_idx ON users(username COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS sessions (
  token         TEXT    PRIMARY KEY CHECK(length(token) = 43),
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  issued_at_ms  INTEGER NOT NULL,
  expires_at_ms INTEGER NOT NULL CHECK(expires_at_ms > issued_at_ms),
  last_seen_ms  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at_ms);

CREATE TABLE IF NOT EXISTS todos (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title           TEXT    NOT NULL CHECK(length(title) BETWEEN 1 AND 500),
  body            TEXT    NOT NULL DEFAULT '' CHECK(length(body) <= 10000),
  done            INTEGER NOT NULL DEFAULT 0 CHECK(done IN (0,1)),
  priority        INTEGER NOT NULL DEFAULT 2 CHECK(priority BETWEEN 1 AND 3),
  created_at_ms   INTEGER NOT NULL,
  updated_at_ms   INTEGER NOT NULL,
  completed_at_ms INTEGER
);

CREATE INDEX IF NOT EXISTS todos_user_done_idx ON todos(user_id, done, created_at_ms DESC);

CREATE TABLE IF NOT EXISTS todo_images (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  todo_id               INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,
  user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content_type          TEXT    NOT NULL
                                CHECK(content_type IN ('image/png','image/jpeg','image/gif','image/webp')),
  byte_count            INTEGER NOT NULL CHECK(byte_count > 0 AND byte_count <= 5242880),
  storage_relative_path TEXT    NOT NULL UNIQUE CHECK(length(storage_relative_path) <= 64),
  uploaded_at_ms        INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS todo_images_todo_idx ON todo_images(todo_id);
