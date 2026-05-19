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

-- Seed a demo user so first-time visitors can log in immediately
-- without registering. Username: demo / password: demo1234.
-- The hash below is a real bcrypt $2b$12$… of "demo1234" generated
-- at build authoring time; regenerate via:
--   ./build/sem_bcrypt_health_demo.exe   (prints a fresh hash)
-- and paste the new value here if you want to rotate the password.
INSERT OR IGNORE INTO users (username, password_hash, display_name, created_at_ms, last_login_ms)
VALUES ('demo',
        '$2b$12$K6EkP0Z.0Q6Fd2Afr86q2ehCYI5bdeJlGa4grVUosJFL9LJextTAu',
        'Demo User',
        strftime('%s','now') * 1000,
        0);

-- Seed a few sample todos for the demo user so the dashboard isn't empty.
INSERT OR IGNORE INTO todos (id, user_id, title, body, done, priority, created_at_ms, updated_at_ms)
SELECT 1, id, 'Try the API at /api/version',
       'Open the home page and hit Sign in with demo/demo1234, then explore.',
       0, 1, strftime('%s','now') * 1000, strftime('%s','now') * 1000
FROM users WHERE username = 'demo';

INSERT OR IGNORE INTO todos (id, user_id, title, body, done, priority, created_at_ms, updated_at_ms)
SELECT 2, id, 'Read the schema',
       'Every column has CHECK / NOT NULL / FOREIGN KEY constraints — strict-by-default.',
       0, 2, strftime('%s','now') * 1000, strftime('%s','now') * 1000
FROM users WHERE username = 'demo';

INSERT OR IGNORE INTO todos (id, user_id, title, body, done, priority, created_at_ms, updated_at_ms)
SELECT 3, id, 'Take a look at main.sem',
       'The whole web app, route table, auth, JSON handling, and SQL is in SemanticScript.',
       1, 3, strftime('%s','now') * 1000, strftime('%s','now') * 1000
FROM users WHERE username = 'demo';
