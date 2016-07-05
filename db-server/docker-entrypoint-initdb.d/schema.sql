DROP TABLE IF EXISTS mappings, dataproviders, bloomingdata, metrics;

CREATE TYPE MAPPINGRESULT AS ENUM ('mapping', 'permutation');

CREATE TABLE mappings (
  -- Just the table index
  id             SERIAL PRIMARY KEY,

  -- The resource identifier
  resource_id    CHAR(48)      NOT NULL UNIQUE,

  -- When was this mapping added
  time_added     TIMESTAMP              DEFAULT current_timestamp,

  time_completed TIMESTAMP     NULL,

  -- currently 1:1, but this could be own table too
  access_token   TEXT          NOT NULL,

  -- if the entity matching has been completed
  ready          BOOL          NOT NULL DEFAULT FALSE,

  schema         JSONB         NOT NULL,

  -- the result as json blob - will be a mapping or permutation
  result         JSONB,

  notes          TEXT,

  -- The paillier public key if the result_type requires it
  public_key     JSONB,

  -- Paillier context includes the base to use when encrypting the
  -- mask.
  paillier_context     JSONB,

  parties        SMALLINT               DEFAULT 2,

  result_type    MAPPINGRESULT NOT NULL
);

CREATE TABLE dataproviders (
  id       SERIAL PRIMARY KEY,

  -- The update token for this data provider
  token    CHAR(48) NOT NULL UNIQUE,

  -- Set after the bloom filter data has been added
  uploaded BOOL     NOT NULL DEFAULT FALSE,

  mapping  INT REFERENCES mappings (id)

);

-- The raw data given by each org
CREATE TABLE bloomingdata (
  id  SERIAL PRIMARY KEY,

  ts  TIMESTAMP DEFAULT current_timestamp,

  dp  INT REFERENCES dataproviders (id),

  -- The receipt token for this data
  token    CHAR(48) NOT NULL UNIQUE,

  -- Store it in the form given
  raw JSONB

  -- Note the number of entries
  -- jsonb_array_length(raw)
);

-- Paillier encrypted mask data when result_type is permutation
CREATE TABLE permutationdata (
  id  SERIAL PRIMARY KEY,

  dp  INT REFERENCES dataproviders (id),

  -- Store it in the form it will be served as.
  raw JSONB
);


-- Calculation metrics
CREATE TABLE metrics (
  id  SERIAL PRIMARY KEY,

  ts  TIMESTAMP DEFAULT current_timestamp,

  -- Comparisons per second
  rate INT
);
