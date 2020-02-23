DROP TABLE
IF EXISTS
projects, runs, dataproviders, bloomingdata, run_results,
similarity_scores, permutations, permutation_masks, metrics,

CASCADE;

DROP TYPE IF EXISTS MAPPINGRESULT;

CREATE TYPE MAPPINGRESULT AS ENUM (
  'groups',
  'permutations',
  'similarity_scores'

);

-- The table of entity matching jobs
CREATE TABLE projects (
  -- Table index
  id                  SERIAL PRIMARY KEY,

  -- The resource identifier
  project_id          CHAR(48)      NOT NULL UNIQUE,

  -- When was this project added
  time_added          TIMESTAMP DEFAULT current_timestamp,

  -- currently 1:1, but this could be own table too
  access_token        TEXT          NOT NULL,

  -- not required by the server, but is shared to all parties
  schema              JSONB         NOT NULL,

  -- Size in bytes of the encoding
  encoding_size  INT    NULL,

  -- human readable name for display purposes
  name                TEXT,
  notes               TEXT,

  parties             SMALLINT  DEFAULT 2,

  result_type         MAPPINGRESULT NOT NULL,

  marked_for_deletion boolean   DEFAULT FALSE,

  uses_blocking       boolean   DEFAULT FALSE
);

CREATE TYPE RUNSTATE AS ENUM (
  'created',
  'queued',
  'running',
  'completed',
  'error'
);

CREATE TABLE runs (
  -- Table index
  id             SERIAL PRIMARY KEY,

  -- The run's resource identifier
  run_id         CHAR(48)         NOT NULL UNIQUE,

  project        CHAR(48) REFERENCES projects (project_id) on DELETE CASCADE,

  -- human readable name for display purposes
  name           TEXT,
  notes          TEXT,

  threshold      double precision NOT NULL,

  state          RUNSTATE         NOT NULL,
  stage          SMALLINT  DEFAULT 1,
  type           TEXT             NOT NULL,

  -- When was this run started/completed
  time_added     TIMESTAMP                 DEFAULT current_timestamp,
  time_started   TIMESTAMP        NULL,
  time_completed TIMESTAMP        NULL

);


CREATE OR REPLACE FUNCTION ready(runs)
-- if the entity matching has been completed
RETURNS bool AS $$
  SELECT $1.state = 'completed'
$$ STABLE LANGUAGE SQL;

-- Describe the state of the upload of the clks to the entity-service.
CREATE TYPE UPLOADEDSTATE AS ENUM (
  'not_started', -- default state, a dataprovider has not tried yet to upload her clks
  'in_progress', -- the upload is in progress, so no-one else should be able to upload at the same time
  'done', -- the clks have been uploaded, it should stay this way
  'error' -- the dataprovider has tried to upload the clks but an error occurred, having this state allows a dataprovider to try again.
);

CREATE TABLE dataproviders (
  id       SERIAL PRIMARY KEY,

  -- The update token for this data provider
  token    CHAR(48) NOT NULL UNIQUE,

  -- Set after the bloom filter data has been added
  uploaded UPLOADEDSTATE     NOT NULL,

  project  CHAR(48) REFERENCES projects (project_id) on DELETE CASCADE
);

CREATE INDEX ON dataproviders (project);
CREATE INDEX ON dataproviders (uploaded);

-- It describes the state of the processing of the uploaded clks.
CREATE TYPE PROCESSEDSTATE AS ENUM (
  'pending', -- waiting for some processing to be done
  'ready', -- processing done
  'error' -- an error occurred during the processing
);

-- The PII data for each dataprovider
CREATE TABLE bloomingdata (
  id    SERIAL PRIMARY KEY,

  ts    TIMESTAMP DEFAULT current_timestamp,

  dp    INT REFERENCES dataproviders (id) on DELETE CASCADE,

  -- The receipt token for this data
  token CHAR(48)    NOT NULL UNIQUE,

  -- Filename for the raw unprocessed uploaded data
  file  CHAR(64)    NOT NULL,

  state PROCESSEDSTATE NOT NULL,

  -- Size in bytes of the uploaded encodings
  encoding_size  INT    NULL,

  -- Number of uploaded encodings
  count  INT         NOT NULL,

  -- Number of blocks uploaded
  block_count INT   NOT NULL DEFAULT 1
);

-- File information for blocks of dataprovider's encodings
CREATE TABLE encodingblocks (
  id    SERIAL PRIMARY KEY,
  dp    INT REFERENCES dataproviders (id) on DELETE CASCADE,
  block_id  CHAR(64)    NOT NULL,

  -- Filename for the block of encodings
  file  CHAR(64)    NOT NULL,

  state PROCESSEDSTATE NOT NULL,

  -- Number of encodings in this block
  count  INT         NOT NULL
);

CREATE INDEX block_index ON encodingblocks USING hash (block_id);

CREATE TABLE run_results (
  -- Just the table index
  id     SERIAL PRIMARY KEY,

  run    CHAR(48) REFERENCES runs (run_id) on DELETE CASCADE,

  -- the mapping result as json blob
  result JSONB
);
CREATE INDEX ON run_results (run);

-- Store the CSV file name containing the similarity scores
CREATE TABLE similarity_scores (
  -- Just the table index
  id   SERIAL PRIMARY KEY,

  run  CHAR(48) REFERENCES runs (run_id) on DELETE CASCADE,

  -- The name of CSV file containing the score results
  file CHAR(70) NOT NULL
);

CREATE INDEX ON similarity_scores (run);

-- There will be 1 permutation per project dp per run
CREATE TABLE permutations (
  id          SERIAL PRIMARY KEY,

  dp          INT REFERENCES dataproviders (id) on DELETE CASCADE,
  run         CHAR(48) REFERENCES runs (run_id) on DELETE CASCADE,

  -- the permutation array as a json blob for this dp
  permutation JSONB
);

-- Mask data for each permutation
CREATE TABLE permutation_masks (
  id      SERIAL PRIMARY KEY,

  project CHAR(48) REFERENCES projects (project_id) on DELETE CASCADE,
  run     CHAR(48) REFERENCES runs (run_id) on DELETE CASCADE,

  -- Store the mask in the json form how it will be served
  -- A list of [0, 1, 0...]
  raw     JSONB
);

-- Calculation metrics
CREATE TABLE metrics (
  id   SERIAL PRIMARY KEY,

  ts   TIMESTAMP DEFAULT current_timestamp,

  -- Comparisons per second
  rate BIGINT
);
