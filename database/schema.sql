DROP TABLE IF EXISTS mappings, dataproviders, bloomingdata;

CREATE TYPE MAPPINGRESULT AS ENUM ('mapping', 'permutation');

CREATE TABLE mappings (
  -- Just the table index
  id             SERIAL PRIMARY KEY,

  -- The resource identifier
  resource_id    CHAR(64)      NOT NULL UNIQUE,

  -- When was this mapping added
  time_added     TIMESTAMP              DEFAULT current_timestamp,

  time_completed TIMESTAMP     NULL,

  -- currently 1:1, but this could be own table too
  access_token   TEXT          NOT NULL,

  -- if the entity matching has been completed
  ready          BOOL          NOT NULL DEFAULT FALSE,

  schema         JSONB         NOT NULL,

  -- the result as json blob - will be a mapping or permutation
  result        JSONB,

  notes          TEXT,

  parties        SMALLINT               DEFAULT 2,

  result_type    MAPPINGRESULT NOT NULL
);

CREATE TABLE dataproviders (
  id       SERIAL PRIMARY KEY,

  -- The update token for this data provider
  token    CHAR(64) NOT NULL UNIQUE,

  -- Set after the bloom filter data has been added
  uploaded BOOL     NOT NULL DEFAULT FALSE,

  mapping  INT REFERENCES mappings (id)

);

CREATE TABLE bloomingdata (
  id  SERIAL PRIMARY KEY,

  ts  TIMESTAMP DEFAULT current_timestamp,

  dp  INT REFERENCES dataproviders (id),

  -- Might as well store it in the form given
  raw JSONB
);
