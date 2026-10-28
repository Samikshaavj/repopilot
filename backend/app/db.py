import psycopg

from app.config import DATABASE_URL


def get_connection():
    """Open a new connection to the Postgres database."""
    return psycopg.connect(DATABASE_URL)