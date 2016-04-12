drop table if exists mappings;

create table mappings (
  id SERIAL primary key,
  name text not null,
  schema text not null,
  notes text
);
