#!/bin/bash
set -e

## If PGURL is not set, construct it from individual environment variables
#if [ -z "$PGURL" ]; then
#  if [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_PASSWORD" ] || [ -z "$POSTGRES_HOST" ] || [ -z "$POSTGRES_DB" ]; then
#    echo "Error: Either PGURL or all of POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_DB must be set." >&2
#    exit 1
#  fi
#  export PGURL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST:5432?sslmode=disable"
#fi
#
#echo "Using PGURL: $PGURL"
#
## 1. Run teardown.sql to drop and recreate the database
#psql "$PGURL" -f pre-script.sql
#
## 2. Run migrate.py to migrate data from MySQL to PostgreSQL
#python3 migrate.py

# If PGURL is not set, construct it from individual environment variables
if [ -z "$PGURL" ]; then
  if [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_PASSWORD" ] || [ -z "$POSTGRES_HOST" ] || [ -z "$POSTGRES_DB" ]; then
    echo "Error: Either PGURL or all of POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_DB must be set." >&2
    exit 1
  fi
  export PGURL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST:5432/$POSTGRES_DB?sslmode=disable"
fi

# 3. Run sql_init.sql to add constraints and triggers
psql "$PGURL" -f post-script.sql
