from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from trackyr.config import cfg

log = logging.getLogger(__name__)

engine = create_engine(
    cfg.database_url,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=3,
    echo=False,
)

SessionFactory = sessionmaker(bind=engine)


def get_session() -> Session:
    return SessionFactory()
