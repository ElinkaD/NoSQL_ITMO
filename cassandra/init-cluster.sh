#!/bin/sh
set -eu

wait_for_cassandra() {
  host="$1"
  port="$2"

  until cqlsh "$host" "$port" -e "SHOW VERSION" >/dev/null 2>&1; do
    sleep 2
  done
}

create_schema() {
  host="$1"
  port="$2"

  cqlsh "$host" "$port" <<EOF
CREATE KEYSPACE IF NOT EXISTS ${CASSANDRA_KEYSPACE}
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE ${CASSANDRA_KEYSPACE};

CREATE TABLE IF NOT EXISTS event_reactions (
    event_id text,
    created_by text,
    like_value tinyint,
    created_at timestamp,
    PRIMARY KEY ((event_id), created_by)
);

CREATE INDEX IF NOT EXISTS event_reactions_created_by_idx ON event_reactions (created_by);
CREATE INDEX IF NOT EXISTS event_reactions_like_value_idx ON event_reactions (like_value);
EOF
}

first_host="$(printf '%s\n' "${CASSANDRA_HOSTS}" | cut -d',' -f1 | tr -d ' ')"

if [ -z "$first_host" ]; then
  echo "CASSANDRA_HOSTS is empty" >&2
  exit 1
fi

wait_for_cassandra "$first_host" "${CASSANDRA_PORT}"
create_schema "$first_host" "${CASSANDRA_PORT}"
