import sqlite3


def init_db():
    conn = sqlite3.connect("results.db")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            name TEXT,
            username TEXT,
            quiz_id TEXT,
            score INTEGER,
            total INTEGER,
            time_taken REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, quiz_id)
        )
    """)

    conn.commit()
    conn.close()


def save_result(user_id, name, username, quiz_id, score, total, time_taken):
    conn = sqlite3.connect("results.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT 1 FROM results
        WHERE user_id = ? AND quiz_id = ?
    """, (user_id, quiz_id))

    exists = cur.fetchone()

    if not exists:
        cur.execute("""
            INSERT INTO results (user_id, name, username, quiz_id, score, total, time_taken)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, name, username, quiz_id, score, total, time_taken))

        conn.commit()

    conn.close()


def get_rank(quiz_id, score, time_taken):
    conn = sqlite3.connect("results.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) FROM results
        WHERE quiz_id = ?
        AND (score > ? OR (score = ? AND time_taken < ?))
    """, (quiz_id, score, score, time_taken))

    better = cur.fetchone()[0]
    conn.close()

    return better + 1


def get_all_results(limit=50):
    conn = sqlite3.connect("results.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT name, username, quiz_id, score, total, time_taken, created_at
        FROM results
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()
    return rows


def get_results_by_quiz(quiz_id, limit=50):
    conn = sqlite3.connect("results.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT name, username, score, total, time_taken, created_at
        FROM results
        WHERE quiz_id = ?
        ORDER BY score DESC, time_taken ASC
        LIMIT ?
    """, (quiz_id, limit))

    rows = cur.fetchall()
    conn.close()
    return rows
