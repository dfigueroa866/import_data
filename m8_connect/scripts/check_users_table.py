import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from sqlalchemy import create_engine, text
from data_staging.config import settings

engine = create_engine(settings.DATABASE_URL)
with engine.connect() as conn:
    columns = conn.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'users' "
            "ORDER BY ordinal_position"
        )
    ).fetchall()
    print("columns:")
    for col in columns:
        print(f"  {col.column_name}: {col.data_type}")

    row = conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'users'"
        )
    ).fetchone()
    print("users table:", row)
    if row:
        count = conn.execute(text("SELECT COUNT(*) FROM public.users")).scalar()
        print("user count:", count)
        status = conn.execute(
            text(
                "SELECT email, failed_login_count, locked_until, (password_hash IS NOT NULL) AS has_pw "
                "FROM public.users LIMIT 5"
            )
        ).fetchall()
        for s in status:
            print(" ", s)
        samples = conn.execute(
            text(
                "SELECT email, (password_hash IS NOT NULL) AS has_pw "
                "FROM public.users LIMIT 5"
            )
        ).fetchall()
        for s in samples:
            print(" ", s)
