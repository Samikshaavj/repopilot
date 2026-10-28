import psycopg
from pgvector.psycopg import register_vector

from app.config import DATABASE_URL


def get_connection():
    """Open a connection that understands the vector column type."""
    conn = psycopg.connect(DATABASE_URL)
    register_vector(conn)
    return conn