from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.SQLALCHEMY_ECHO,
    # pool_pre_ping issues a cheap SELECT 1 before handing out a
    # pooled connection, transparently discarding and replacing one
    # that the database has since closed (idle timeout, restart,
    # failover) instead of surfacing "server closed the connection
    # unexpectedly" as a request failure. pool_recycle bounds how long
    # a connection can live in the pool at all, for the same reason -
    # both are standard hardening for a long-running production
    # process against a managed database that can recycle connections
    # server-side without warning.
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
