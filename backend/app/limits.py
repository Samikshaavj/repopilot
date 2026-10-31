import hashlib

from fastapi import HTTPException, Request

from app.config import IP_HASH_SALT, QUESTIONS_PER_DAY, QUESTIONS_PER_IP_PER_HOUR
from app.db import get_connection


def client_ip(request: Request) -> str:
    """The visitor's address.

    Behind a proxy (like a hosting platform's load balancer) we trust the LAST entry of
    X-Forwarded-For, which the proxy added itself. Earlier entries can be forged by the visitor.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def hash_ip(ip: str) -> str:
    """We never store raw addresses, only a salted hash."""
    return hashlib.sha256(f"{IP_HASH_SALT}:{ip}".encode()).hexdigest()


def check_question_allowed(request: Request) -> None:
    """Raise HTTP 429 if this visitor, or the whole site, asked too much. Otherwise record this question."""
    ip_hash = hash_ip(client_ip(request))
    with get_connection() as conn:
        conn.execute("DELETE FROM question_log WHERE created_at < now() - interval '2 days'")
        per_visitor = conn.execute(
            "SELECT count(*) FROM question_log WHERE ip_hash = %s AND created_at > now() - interval '1 hour'",
            (ip_hash,),
        ).fetchone()[0]
        today = conn.execute(
            "SELECT count(*) FROM question_log WHERE created_at > now() - interval '1 day'"
        ).fetchone()[0]

        if per_visitor >= QUESTIONS_PER_IP_PER_HOUR:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"You have used your {QUESTIONS_PER_IP_PER_HOUR} new questions for this hour. "
                    "Saved answers are still available."
                ),
                headers={"Retry-After": "3600"},
            )
        if today >= QUESTIONS_PER_DAY:
            raise HTTPException(
                status_code=429,
                detail=(
                    "The free daily question budget for this demo is used up. Try again tomorrow, "
                    "or open one of the suggested questions, whose answers are saved."
                ),
                headers={"Retry-After": "3600"},
            )
        conn.execute("INSERT INTO question_log (ip_hash) VALUES (%s)", (ip_hash,))