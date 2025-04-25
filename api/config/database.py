from sqlmodel import create_engine, Session
from api.config.settings import get_env

url = get_env().DATABASE_URL


def get_db():
    engine = create_engine(url, pool_recycle=3600, pool_size=10, max_overflow=5)
    with Session(engine, expire_on_commit=False) as session:
        yield session
