from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infra.config import settings
from app.infra.errors import DatabaseError
from app.db.models import Base, ChatMessage

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db() -> None:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        raise DatabaseError(str(e))

def save_chat(message: str, response: str) -> None:
    try:
        with SessionLocal() as session:
            session.add(ChatMessage(message=message, response=response))
            session.commit()
    except Exception as e:
        raise DatabaseError(str(e))
