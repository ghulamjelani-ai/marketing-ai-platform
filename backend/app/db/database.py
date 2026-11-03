from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=settings.DB_USER,
    password=settings.DB_PASSWORD,
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    database=settings.DB_NAME,
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def create_db_tables():
    from app.models.models import User, Conversation, Message

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


# create_all makes new tables but never changes existing ones. Columns added later
# to an existing table are listed here and added once.
LATER_COLUMNS = {
    "login_otps": {"locked_until": "TIMESTAMP NULL"},
}


def _add_missing_columns():
    from sqlalchemy import inspect, text

    inspector = inspect(engine)

    with engine.begin() as connection:
        for table, columns in LATER_COLUMNS.items():
            if not inspector.has_table(table):
                continue

            present = {column["name"] for column in inspector.get_columns(table)}

            for name, sql_type in columns.items():
                if name not in present:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))