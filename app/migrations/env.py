from alembic import context
from app.models import Base

connection = context.config.attributes.get('connection')
if connection is None:
    raise RuntimeError('Use python -m app.cli migrate to supply the configured database connection')
context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
