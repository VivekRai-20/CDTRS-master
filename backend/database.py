import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from dotenv import load_dotenv

load_dotenv()

# =========================================================
# DATABASE URL
# Read from environment variable DATABASE_URL.
# If not set, fall back to localhost development default.
# Replace <your_password> with your PostgreSQL password in
# the .env file:
#   DATABASE_URL=postgresql+psycopg2://postgres:<your_password>@localhost:5432/cdtrs
# =========================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:fctd@localhost:5432/cdtrs"
)

# Cloud providers (e.g. Render, Railway, Neon, Supabase) often provide URLs starting with "postgres://"
# SQLAlchemy requires "postgresql+psycopg2://" or "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+psycopg2://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(
    DATABASE_URL,
    echo=False         # Set True for SQL query logging during debug
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


# =========================================================
# DB SESSION DEPENDENCY (FastAPI)
# =========================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()

def ensure_enum_compatibility(engine):
    try:
        if engine.dialect.name != "postgresql": return
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'priority_enum') THEN ALTER TYPE priority_enum ADD VALUE IF NOT EXISTS 'CRITICAL'; END IF; END $$;"))
    except Exception:
        pass


# Columns added to existing tables after the first release.  create_all()
# only creates missing tables; it never adds columns to a table that already
# exists, so older databases need these added explicitly.
_ADDED_COLUMNS = [
    ("routing_suggestions", "ranked_departments", "JSON"),
]


def ensure_schema_columns(engine):
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        with engine.begin() as conn:
            for table, column, ddl_type in _ADDED_COLUMNS:
                if table not in tables:
                    continue
                existing = {c["name"] for c in inspector.get_columns(table)}
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
                    print(f"[STARTUP] Added missing column {table}.{column}", flush=True)
    except Exception as exc:
        print(f"[STARTUP WARN] Schema column check failed: {exc}", flush=True)
