from app.db import get_connection


def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            print(cur.fetchone()[0])

            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
            print("pgvector installed:", cur.fetchone() is not None)

            cur.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
            )
            print("tables in database:", cur.fetchone()[0])


if __name__ == "__main__":
    main()