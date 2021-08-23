"""add err_msg to runs

Revision ID: e321799791b7
Revises: 292d2f2d3939
Create Date: 2021-02-25 16:40:29.151969

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e321799791b7'
down_revision = '292d2f2d3939'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('runs', sa.Column('error_msg', sa.Text, nullable=True))


def downgrade():
    op.drop_column('runs', 'error_msg')
