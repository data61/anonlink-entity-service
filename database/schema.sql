
DROP TABLE IF EXISTS mappings, dataproviders, bloomingdata;

CREATE TABLE mappings (
  -- Just the table index
  id           SERIAL PRIMARY KEY,

  -- The resource identifier
  resource_id  CHAR(64) NOT NULL UNIQUE,

  -- currently 1:1, but this could be own table too
  access_token TEXT     NOT NULL,

  -- if the entity matching has been completed
  ready        BOOL     NOT NULL DEFAULT FALSE,

  schema       JSONB    NOT NULL,

  -- the result
  mapping      JSONB,

  notes        TEXT,

  parties      SMALLINT DEFAULT 2
);

CREATE TABLE dataproviders (
  id      SERIAL PRIMARY KEY,

  -- The update token for this data provider
  token   CHAR(64) NOT NULL UNIQUE,


  -- Set after the bloom filter data has been added
  uploaded   BOOL      NOT NULL DEFAULT FALSE,

  mapping INT REFERENCES mappings (id)

);

CREATE TABLE bloomingdata (
  id  SERIAL PRIMARY KEY,

  dp  INT REFERENCES dataproviders (id),

  -- Might as well store it as given (JSONB)
  raw JSONB
);
