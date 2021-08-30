import enum

from sqlalchemy import BigInteger, Boolean, CHAR, Column, DateTime, Enum, Float, ForeignKey, Index, Integer, LargeBinary, SmallInteger, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship


from entityservice.database.base_class import Base


class Encoding(Base):
    __tablename__ = 'encodings'

    encoding_id = Column(BigInteger, primary_key=True)
    encoding = Column(LargeBinary, nullable=False)
    dp = Column(ForeignKey('dataproviders.id', ondelete='CASCADE'))


class Metric(Base):
    __tablename__ = 'metrics'

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    rate = Column(BigInteger)


class ProjectResultType(str, enum.Enum):
    groups = 'groups'
    permutations = 'permutations'
    similarity_scores = 'similarity_scores'


class Project(Base):
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True)
    project_id = Column(CHAR(48), nullable=False, unique=True)
    time_added = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    access_token = Column(Text, nullable=False)
    schema = Column(JSONB(astext_type=Text()), nullable=False)
    encoding_size = Column(Integer)
    name = Column(Text)
    notes = Column(Text)
    parties = Column(SmallInteger, server_default=text("2"))
    result_type = Column(Enum(ProjectResultType, name='mappingresult'), nullable=False)
    marked_for_deletion = Column(Boolean, server_default=text("false"))
    uses_blocking = Column(Boolean, server_default=text("false"))


class DataProviderUploadStatus(str, enum.Enum):
    not_started = 'not_started'
    in_progress = 'in_progress'
    done = 'done'
    error = 'error'


class Dataprovider(Base):
    __tablename__ = 'dataproviders'

    id = Column(Integer, primary_key=True)
    token = Column(CHAR(48), nullable=False, unique=True)
    uploaded = Column(Enum(DataProviderUploadStatus, name='uploadedstate'), nullable=False, index=True)
    project = Column(ForeignKey('projects.project_id', ondelete='CASCADE'), index=True)

    project1 = relationship('Project')


class RunState(str, enum.Enum):
    created = 'created'
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    error = 'error'


class Run(Base):
    __tablename__ = 'runs'

    id = Column(Integer, primary_key=True)
    run_id = Column(CHAR(48), nullable=False, unique=True)
    project = Column(ForeignKey('projects.project_id', ondelete='CASCADE'))
    name = Column(Text)
    notes = Column(Text)
    threshold = Column(Float(53), nullable=False)
    state = Column(Enum(RunState, name='runstate'), nullable=False, default=RunState.created)
    stage = Column(SmallInteger, server_default=text("1"))
    type = Column(Text, nullable=False)
    time_added = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    time_started = Column(DateTime)
    time_completed = Column(DateTime)
    error_msg = Column(Text, nullable=True)

    project1 = relationship('Project')


class BlockState(str, enum.Enum):
    pending = 'pending'
    ready = 'ready'
    error = 'error'


class Block(Base):
    __tablename__ = 'blocks'
    __table_args__ = (
        Index('blocks_dp_block_name_idx', 'dp', 'block_name'),
    )

    dp = Column(ForeignKey('dataproviders.id', ondelete='CASCADE'))
    block_name = Column(CHAR(64), nullable=False)
    block_id = Column(Integer, primary_key=True)
    count = Column(Integer, nullable=False)
    state = Column(Enum(BlockState, name='processedstate'), nullable=False)

    dataprovider = relationship('Dataprovider')


class PermutationMask(Base):
    __tablename__ = 'permutation_masks'

    id = Column(Integer, primary_key=True)
    project = Column(ForeignKey('projects.project_id', ondelete='CASCADE'))
    run = Column(ForeignKey('runs.run_id', ondelete='CASCADE'))
    raw = Column(JSONB())

    project1 = relationship('Project')
    run1 = relationship('Run')


class Permutation(Base):
    __tablename__ = 'permutations'

    id = Column(Integer, primary_key=True)
    dp = Column(ForeignKey('dataproviders.id', ondelete='CASCADE'))
    run = Column(ForeignKey('runs.run_id', ondelete='CASCADE'))
    permutation = Column(JSONB())

    dataprovider = relationship('Dataprovider')
    run1 = relationship('Run')


class RunResult(Base):
    __tablename__ = 'run_results'

    id = Column(Integer, primary_key=True)
    # TODO this was the only column change from run -> run_id
    run_id = Column(ForeignKey('runs.run_id', ondelete='CASCADE'), index=True)
    result = Column(JSONB())

    run = relationship('Run')


class SimilarityScore(Base):
    __tablename__ = 'similarity_scores'

    id = Column(Integer, primary_key=True)
    run = Column(ForeignKey('runs.run_id', ondelete='CASCADE'), index=True)
    file = Column(CHAR(70), nullable=False)

    run1 = relationship('Run')


class UploadState(str, enum.Enum):
    pending = 'pending'
    ready = 'ready'
    error = 'error'


class Upload(Base):
    __tablename__ = 'uploads'

    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    dp = Column(ForeignKey('dataproviders.id', ondelete='CASCADE'))
    token = Column(CHAR(48), nullable=False, unique=True)
    file = Column(CHAR(64))
    state = Column(Enum(UploadState, name='processedstate'), nullable=False)
    encoding_size = Column(Integer)
    count = Column(Integer, nullable=False)
    block_count = Column(Integer, nullable=False, server_default=text("1"))

    dataprovider = relationship('Dataprovider')


t_encodingblocks = Table(
    'encodingblocks',
    Base.metadata,
    Column('dp', ForeignKey('dataproviders.id', ondelete='CASCADE')),
    Column('entity_id', Integer),
    Column('encoding_id', ForeignKey('encodings.encoding_id', ondelete='CASCADE'), index=True),
    Column('block_id', ForeignKey('blocks.block_id'), index=True)
)
