#!/bin/sh
# Runs once, on the first start of an empty volume: the database for integration tests
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "CREATE DATABASE \"${POSTGRES_TEST_DB:-shifts_test}\";"
