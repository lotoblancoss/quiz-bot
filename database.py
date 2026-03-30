import os
from typing import Any

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задан")
    return psycopg.connect(DATABASE_URL)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name TEXT,
                    username TEXT,
                    quiz_id TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    total INTEGER NOT NULL,
                    time_taken DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, quiz_id)
                )
            """)
        conn.commit()


def save_result(user_id, name, username, quiz_id, score, total, time_taken):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1
                FROM results
                WHERE user_id = %s AND quiz_id = %s
            """, (user_id, quiz_id))

            exists = cur.fetchone()

            if not exists:
                cur.execute("""
                    INSERT INTO results (user_id, name, username, quiz_id, score, total, time_taken)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (user_id, name, username, quiz_id, score, total, time_taken))
        conn.commit()


def get_rank(quiz_id, score, time_taken):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM results
                WHERE quiz_id = %s
                  AND (score > %s OR (score = %s AND time_taken < %s))
            """, (quiz_id, score, score, time_taken))
            better = cur.fetchone()[0]
    return better + 1


def get_all_results(limit=50):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT name, username, quiz_id, score, total, time_taken, created_at
                FROM results
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
    return rows


def get_results_by_quiz(quiz_id, limit=50):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT name, username, score, total, time_taken, created_at
                FROM results
                WHERE quiz_id = %s
                ORDER BY score DESC, time_taken ASC
                LIMIT %s
            """, (quiz_id, limit))
            rows = cur.fetchall()
    return rows
