"""case number per court

Revision ID: 26bc3a2b11fb
Revises: 613a08f7ad73
Create Date: 2026-01-20 20:07:23.098456

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '26bc3a2b11fb'
down_revision = '613a08f7ad73'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite can't drop a UNIQUE constraint in-place.
    # We'll rebuild tblcase with the desired UNIQUE(court_id, case_number)
    # and migrate the data.

    with op.batch_alter_table('tblcase', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint('uq_case_number', type_='unique')
        batch_op.create_unique_constraint('uq_case_number_per_court', ['court_id', 'case_number'])


def downgrade():
    # revert back to UNIQUE(case_number)
    with op.batch_alter_table('tblcase', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint('uq_case_number_per_court', type_='unique')
        batch_op.create_unique_constraint('uq_case_number', ['case_number'])
