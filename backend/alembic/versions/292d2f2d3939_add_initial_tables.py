"""Add initial tables

Revision ID: 292d2f2d3939
Revises: 
Create Date: 2021-02-09 11:33:25.718643

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '292d2f2d3939'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('encodings',
    sa.Column('encoding_id', sa.BigInteger(), nullable=False),
    sa.Column('encoding', sa.LargeBinary(), nullable=False),
    sa.PrimaryKeyConstraint('encoding_id')
    )
    op.create_table('metrics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.Column('rate', sa.BigInteger(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.CHAR(length=48), nullable=False),
    sa.Column('time_added', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.Column('access_token', sa.Text(), nullable=False),
    sa.Column('schema', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('encoding_size', sa.Integer(), nullable=True),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('parties', sa.SmallInteger(), server_default=sa.text('2'), nullable=True),
    sa.Column('result_type', sa.Enum('groups', 'permutations', 'similarity_scores', name='mappingresult'), nullable=False),
    sa.Column('marked_for_deletion', sa.Boolean(), server_default=sa.text('false'), nullable=True),
    sa.Column('uses_blocking', sa.Boolean(), server_default=sa.text('false'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id')
    )
    op.create_table('dataproviders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token', sa.CHAR(length=48), nullable=False),
    sa.Column('uploaded', sa.Enum('not_started', 'in_progress', 'done', 'error', name='uploadedstate'), nullable=False),
    sa.Column('project', sa.CHAR(length=48), nullable=True),
    sa.ForeignKeyConstraint(['project'], ['projects.project_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    op.create_index(op.f('ix_dataproviders_project'), 'dataproviders', ['project'], unique=False)
    op.create_index(op.f('ix_dataproviders_uploaded'), 'dataproviders', ['uploaded'], unique=False)
    op.create_table('runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.CHAR(length=48), nullable=False),
    sa.Column('project', sa.CHAR(length=48), nullable=True),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('threshold', sa.Float(precision=53), nullable=False),
    sa.Column('state', sa.Enum('created', 'queued', 'running', 'completed', 'error', name='runstate'), nullable=False),
    sa.Column('stage', sa.SmallInteger(), server_default=sa.text('1'), nullable=True),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('time_added', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.Column('time_started', sa.DateTime(), nullable=True),
    sa.Column('time_completed', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project'], ['projects.project_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id')
    )
    op.create_table('blocks',
    sa.Column('dp', sa.Integer(), nullable=True),
    sa.Column('block_name', sa.CHAR(length=64), nullable=False),
    sa.Column('block_id', sa.Integer(), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.Column('state', sa.Enum('pending', 'ready', 'error', name='processedstate'), nullable=False),
    sa.ForeignKeyConstraint(['dp'], ['dataproviders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('block_id')
    )
    op.create_index('blocks_dp_block_name_idx', 'blocks', ['dp', 'block_name'], unique=False)
    op.create_table('permutation_masks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project', sa.CHAR(length=48), nullable=True),
    sa.Column('run', sa.CHAR(length=48), nullable=True),
    sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['project'], ['projects.project_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run'], ['runs.run_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('permutations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dp', sa.Integer(), nullable=True),
    sa.Column('run', sa.CHAR(length=48), nullable=True),
    sa.Column('permutation', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['dp'], ['dataproviders.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run'], ['runs.run_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('run_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.CHAR(length=48), nullable=True),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['runs.run_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_run_results_run_id'), 'run_results', ['run_id'], unique=False)
    op.create_table('similarity_scores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run', sa.CHAR(length=48), nullable=True),
    sa.Column('file', sa.CHAR(length=70), nullable=False),
    sa.ForeignKeyConstraint(['run'], ['runs.run_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_similarity_scores_run'), 'similarity_scores', ['run'], unique=False)
    op.create_table('uploads',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.Column('dp', sa.Integer(), nullable=True),
    sa.Column('token', sa.CHAR(length=48), nullable=False),
    sa.Column('file', sa.CHAR(length=64), nullable=True),
    sa.Column('state', sa.Enum('pending', 'ready', 'error', name='processedstate'), nullable=False),
    sa.Column('encoding_size', sa.Integer(), nullable=True),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.Column('block_count', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.ForeignKeyConstraint(['dp'], ['dataproviders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
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


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_encodingblocks_encoding_id'), table_name='encodingblocks')
    op.drop_index(op.f('ix_encodingblocks_block_id'), table_name='encodingblocks')
    op.drop_table('encodingblocks')
    op.drop_table('uploads')
    op.drop_index(op.f('ix_similarity_scores_run'), table_name='similarity_scores')
    op.drop_table('similarity_scores')
    op.drop_index(op.f('ix_run_results_run_id'), table_name='run_results')
    op.drop_table('run_results')
    op.drop_table('permutations')
    op.drop_table('permutation_masks')
    op.drop_index('blocks_dp_block_name_idx', table_name='blocks')
    op.drop_table('blocks')
    op.drop_table('runs')
    op.drop_index(op.f('ix_dataproviders_uploaded'), table_name='dataproviders')
    op.drop_index(op.f('ix_dataproviders_project'), table_name='dataproviders')
    op.drop_table('dataproviders')
    op.drop_table('projects')
    op.drop_table('metrics')
    op.drop_table('encodings')
    # ### end Alembic commands ###