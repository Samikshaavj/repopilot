import json
import re

from app.db import get_connection


def normalize_question(question: str) -> str:
    """'  How does   Key rotation work?? '  ->  'how does key rotation work'"""
    text = re.sub(r"\s+", " ", question.strip().lower())
    return text.rstrip("?.! ")


def get_cached(repo_id: int, question: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT answer, steps, tokens FROM answer_cache WHERE repo_id = %s AND question_key = %s",
            (repo_id, normalize_question(question)),
        ).fetchone()
    if row is None:
        return None
    return {"answer": row[0], "steps": row[1], "tokens": row[2] or 0}


def save_answer(repo_id: int, question: str, answer: str, steps: list, tokens: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO answer_cache (repo_id, question_key, answer, steps, tokens)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (repo_id, question_key) DO UPDATE
               SET answer = EXCLUDED.answer, steps = EXCLUDED.steps,
                   tokens = EXCLUDED.tokens, created_at = now()""",
            (repo_id, normalize_question(question), answer, json.dumps(steps), tokens),
        )