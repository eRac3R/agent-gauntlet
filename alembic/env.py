from alembic import context

from gauntlet.db import Base, get_engine

target_metadata = Base.metadata


def run_migrations_online() -> None:
    # ensure_schema() hands us a live connection; the alembic CLI does not.
    connection = context.config.attributes.get("connection")
    if connection is None:
        with get_engine().begin() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    else:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
