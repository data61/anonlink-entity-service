DROP TABLE IF EXISTS projects, runs, dataproviders, bloomingdata, run_results, similarity_scores, permutations, permutation_masks, metrics;

CREATE TYPE MAPPINGRESULT AS ENUM (
  'mapping',
  'permutations',
  'similarity_scores'
);

-- The table of entity matching jobs
CREATE TABLE projects (
  -- Table index
  id           SERIAL PRIMARY KEY,

  -- The resource identifier
  project_id   CHAR(48)      NOT NULL UNIQUE,

  -- When was this project added
  time_added   TIMESTAMP DEFAULT current_timestamp,

  -- currently 1:1, but this could be own table too
  access_token TEXT          NOT NULL,

  -- not required by the server, but is shared to all parties
  schema       JSONB         NOT NULL,

  -- human readable name for display purposes
  name         TEXT,
  notes        TEXT,

  parties      SMALLINT  DEFAULT 2,

  result_type  MAPPINGRESULT NOT NULL

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

  chunk_size     BIGINT           NOT NULL DEFAULT -1,

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


CREATE TABLE dataproviders (
  id       SERIAL PRIMARY KEY,

  -- The update token for this data provider
  token    CHAR(48) NOT NULL UNIQUE,

  -- Set after the bloom filter data has been added
  uploaded BOOL     NOT NULL DEFAULT FALSE,

  project  CHAR(48) REFERENCES projects (project_id) on DELETE CASCADE
);

CREATE INDEX ON dataproviders (project);
CREATE INDEX ON dataproviders (uploaded);

CREATE TYPE UPLOADSTATE AS ENUM (
  'pending',
  'ready',
  'error'
);

-- The uploaded CLK data for each dataprovider
CREATE TABLE bloomingdata (
  id    SERIAL PRIMARY KEY,

  ts    TIMESTAMP DEFAULT current_timestamp,

  dp    INT REFERENCES dataproviders (id) on DELETE CASCADE,

  -- The receipt token for this data
  token CHAR(48)    NOT NULL UNIQUE,

  -- Store the raw CLK data in a file
  file  CHAR(64)    NOT NULL,

  state UPLOADSTATE NOT NULL,

  size  INT         NOT NULL
);


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
  run     CHAR(48) REFERENCES runs (run_id),

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
