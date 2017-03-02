DROP TABLE IF EXISTS mappings, dataproviders, bloomingdata, metrics;

CREATE TYPE MAPPINGRESULT AS ENUM (
  'mapping',
  'permutation',
  'permutation_unencrypted_mask');


-- The table of entity matching jobs
CREATE TABLE mappings (
  -- Just the table index
  id             SERIAL PRIMARY KEY,

  -- The resource identifier
  resource_id    CHAR(48)      NOT NULL UNIQUE,

  -- When was this mapping added
  time_added     TIMESTAMP              DEFAULT current_timestamp,

  time_started TIMESTAMP       NULL,

  time_completed TIMESTAMP     NULL,

  -- currently 1:1, but this could be own table too
  access_token   TEXT          NOT NULL,

  -- if the entity matching has been completed
  ready          BOOL          NOT NULL DEFAULT FALSE,

  -- not required by the server, but is shared to all parties
  schema         JSONB         NOT NULL,

  notes          TEXT,

  parties        SMALLINT               DEFAULT 2,

  result_type    MAPPINGRESULT NOT NULL
);

CREATE TABLE dataproviders (
  id       SERIAL PRIMARY KEY,

  -- The update token for this data provider
  token    CHAR(48) NOT NULL UNIQUE,

  -- Set after the bloom filter data has been added
  uploaded BOOL     NOT NULL DEFAULT FALSE,

  -- TODO consider referring to mapping by resource-id
  mapping  INT REFERENCES mappings (id)
);

CREATE INDEX ON dataproviders (mapping);
CREATE INDEX ON dataproviders (uploaded);

CREATE TYPE UPLOADSTATE AS ENUM (
  'pending',
  'ready',
  'error'
);

-- The uploaded CLK data for each dataprovider
CREATE TABLE bloomingdata (
  id  SERIAL PRIMARY KEY,

  ts  TIMESTAMP DEFAULT current_timestamp,

  dp  INT REFERENCES dataproviders (id),

  -- The receipt token for this data
  token    CHAR(48) NOT NULL UNIQUE,

  -- Store the raw CLK data in a file
  file     CHAR(64) NOT NULL,

  state     UPLOADSTATE NOT NULL,

  size  INT NOT NULL
);


CREATE TABLE mapping_results (
  -- Just the table index
  id          SERIAL PRIMARY KEY,

  mapping     CHAR(48) REFERENCES mappings (resource_id),

  -- the mapping result as json blob
  result      JSONB
);


-- For now there will be only 1 permutation per mapping
CREATE TABLE permutations (
  id  SERIAL PRIMARY KEY,

  dp  INT REFERENCES dataproviders (id),

  -- the permutation array as a json blob for this dp
  permutation      JSONB
);

-- Mask data for each permutation
CREATE TABLE permutation_masks (
  id  SERIAL PRIMARY KEY,

  mapping  CHAR(48) REFERENCES mappings (resource_id),

  -- Store the mask in the json form how it will be served
  -- A list of [0, 1, 0...]
  raw   JSONB
);


-- Information required for the encrypted types
CREATE TABLE paillier (
    id  SERIAL PRIMARY KEY,

    -- The paillier public key if the result_type requires it
    public_key     JSONB,

    -- Paillier context includes the base to use when encrypting the
    -- mask.
    context     JSONB

);

-- Encrypted mask data
CREATE TABLE encrypted_permutation_masks (
  id  SERIAL PRIMARY KEY,

  mapping  CHAR(48) REFERENCES mappings (resource_id),

  paillier  INT REFERENCES paillier (id),

  -- Store it in the json form how it will be served
  raw JSONB
);

-- Calculation metrics
CREATE TABLE metrics (
  id  SERIAL PRIMARY KEY,

  ts  TIMESTAMP DEFAULT current_timestamp,

  -- Comparisons per second
  rate INT
);
