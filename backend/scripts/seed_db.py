"""
Optional local/demo data seed script. Not wired into any startup path
(Dockerfile CMD, lifespan, migrations) - run it explicitly when you
want one:

    cd backend
    python scripts/seed_db.py

Idempotent: safe to run more than once, it skips anything that
already exists rather than erroring or duplicating rows. Creates
exactly one demo user - meetings/resources/etc. are best created
through the app itself (AI Assistant / Smart Scheduler) against that
account, rather than fabricated here in a way that could drift from
the real create_meeting validation rules (conflict detection, resource
availability, etc.) as the app evolves.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.hashing import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402, F401 - registers every model so User's relationship() string references resolve
from app.db.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password-123"
DEMO_NAME = "Demo User"


def seed() -> None:
    db = SessionLocal()

    try:
        existing = db.query(User).filter(User.email == DEMO_EMAIL).first()

        if existing is not None:
            print(f"Demo user already exists (id={existing.id}, email={DEMO_EMAIL}) - nothing to do.")
            return

        user = User(
            name=DEMO_NAME,
            email=DEMO_EMAIL,
            hashed_password=hash_password(DEMO_PASSWORD),
            timezone="UTC",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        print(f"Created demo user id={user.id}")
        print(f"  email:    {DEMO_EMAIL}")
        print(f"  password: {DEMO_PASSWORD}")
        print("Sign in with these at the frontend's /login page.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
