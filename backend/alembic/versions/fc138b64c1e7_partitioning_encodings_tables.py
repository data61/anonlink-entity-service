"""partitioning encodings tables

Revision ID: fc138b64c1e7
Revises: 9a5d78339327
Create Date: 2021-09-10 17:25:36.706874

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fc138b64c1e7'
down_revision = '9a5d78339327'
branch_labels = None
depends_on = None


def upgrade():

    op.drop_constraint('fk_encoding_dp', 'encodings', type_='foreignkey')
    op.drop_constraint('encodingblocks_encoding_id_fkey', 'encodingblocks', type_='foreignkey')
    op.drop_table('encodings')
    op.create_table('encodings',
                    sa.Column('encoding_id', sa.BigInteger(), nullable=False),
                    sa.Column('encoding', sa.LargeBinary(), nullable=False),
                    sa.Column('dp', sa.Integer(), nullable=False),
                    sa.PrimaryKeyConstraint('encoding_id', 'dp'),
                    postgresql_partition_by='LIST (dp)'
                    )

    op.drop_index(op.f('ix_encodingblocks_encoding_id'), table_name='encodingblocks')
    op.drop_index(op.f('ix_encodingblocks_block_id'), table_name='encodingblocks')
    op.drop_table('encodingblocks')
    op.create_table('encodingblocks',
                    sa.Column('dp', sa.Integer(), nullable=False),
                    sa.Column('entity_id', sa.Integer(), nullable=True),
                    sa.Column('encoding_id', sa.BigInteger(), nullable=False),
                    sa.Column('block_id', sa.Integer(), nullable=True),
                    sa.ForeignKeyConstraint(['block_id'], ['blocks.block_id'], ),
                    postgresql_partition_by='LIST (dp)'
                    )
    op.create_index(op.f('ix_encodingblocks_block_id'), 'encodingblocks', ['block_id'], unique=False)
    op.create_index(op.f('ix_encodingblocks_encoding_id'), 'encodingblocks', ['encoding_id'], unique=False)


    # ### end Alembic commands ###

def downgrade():
    op.drop_table('encodings')
    op.create_table('encodings',
                    sa.Column('encoding_id', sa.BigInteger(), nullable=False),
                    sa.Column('encoding', sa.LargeBinary(), nullable=False),
                    sa.Column('dp', sa.Integer(), nullable=True),
                    sa.PrimaryKeyConstraint('encoding_id')
                    )
    op.create_foreign_key('fk_encoding_dp', 'encodings', 'dataproviders', ['dp'], ['id'], ondelete='CASCADE')

    op.drop_index(op.f('ix_encodingblocks_encoding_id'), table_name='encodingblocks')
    op.drop_index(op.f('ix_encodingblocks_block_id'), table_name='encodingblocks')
    op.drop_table('encodingblocks')

    op.create_table('encodingblocks',
                    sa.Column('dp', sa.Integer(), nullable=True),
                    sa.Column('entity_id', sa.Integer(), nullable=True),
                    sa.Column('encoding_id', sa.BigInteger(), nullable=True),
                    sa.Column('block_id', sa.Integer(), nullable=True),
                    sa.ForeignKeyConstraint(['block_id'], ['blocks.block_id'], ),
                    sa.ForeignKeyConstraint(['dp'], ['dataproviders.id'], ondelete='CASCADE'),
                    sa.ForeignKeyConstraint(['encoding_id'], ['encodings.encoding_id'], ondelete='CASCADE')
                    )
    op.create_index(op.f('ix_encodingblocks_block_id'), 'encodingblocks', ['block_id'], unique=False)
    op.create_index(op.f('ix_encodingblocks_encoding_id'), 'encodingblocks', ['encoding_id'], unique=False)
    # ### end Alembic commands ###
