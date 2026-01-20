from alembic import op
import sqlalchemy as sa

def upgrade():
    op.execute("UPDATE tblcase SET status = 'in session' WHERE status = 'in_session'")

def downgrade():
    op.execute("UPDATE tblcase SET status = 'in_session' WHERE status = 'in session'")