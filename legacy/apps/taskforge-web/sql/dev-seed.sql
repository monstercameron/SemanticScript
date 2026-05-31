-- Development seed data — installed ONLY when build.sem declares
-- `buildConstant todoWebPro applyDevSeed String "yes"`.
-- Production builds set applyDevSeed to "no" so the publicly-known demo
-- account is NOT installed; an attacker who reads this repo cannot then
-- log into a production deployment as `demo/demo1234`.
--
-- The bcrypt hash below is a real $2b$12$ hash of "demo1234" generated
-- at authoring time; rotate by editing this file (regenerate via
-- ./build/sem_bcrypt_health_demo.exe) when you want a new shared dev
-- credential.

INSERT OR IGNORE INTO users (username, password_hash, display_name, created_at_ms, last_login_ms)
VALUES ('demo',
        '$2b$12$K6EkP0Z.0Q6Fd2Afr86q2ehCYI5bdeJlGa4grVUosJFL9LJextTAu',
        'Demo User',
        strftime('%s','now') * 1000,
        0);

-- Sample todos so the demo dashboard isn't empty.
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
