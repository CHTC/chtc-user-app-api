## Release

```shell
docker build --platform linux/amd64 -t hub.opensciencegrid.org/chtc/chtc-user-app-api:active_field .
```

```shell
docker push hub.opensciencegrid.org/chtc/chtc-user-app-api:active_field
```

```shell
docker run -it -p 8000:8000 hub.opensciencegrid.org/opensciencegrid/chtc-userapp-api:latest
```

## Run the NGINX server that sits in front of the webhook

```shell
docker run -it -p 80:80 -v ${PWD}/srv:/srv  -v ${PWD}/nginx.conf:/etc/nginx/nginx.conf:ro nginx
```
## Query Parser Docs

All list endpoints in the api allow filtering based on url parameters.

The format for a query is:

```
<column_name>=<comparator>.<value>
```

So to query a user with netid equal to `clock` they url would be `/users?netid=eq.clock`.

All comparators are ["not", "eq", "lt", "le", "gt", "ge", "ne", "like", "ilike", "in", "is"].

In the case of `not` you must use it in conjunction with another comparator, such as `/users?netid=not.like.clock`.

`like` and `ilike` automatically have their values sandwiched between % so `/users?netid=like.clock` is equivalent to `netid LIKE '%clock%'`.

All comparators are automatically combined with `AND`. 

Example:

`/users?netid=not.like.clock&username=not.eq.cannonlock` is the SQL equivalent to `NOT netid LIKE '%clock%' AND NOT username = 'cannonlock'`.

### Ordering

Ordering format is:

```
<column_name>=order_by.<asc | desc>
```

For example:

```
https://userapp.chtc.wisc.edu/api/users?page=0&page_size=50&date=order_by.desc
```

### Tests

Requires Docker (for a throwaway Postgres) and Python 3.12.

First-time setup — create the virtualenv and install dependencies:

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Then run the full suite:

```
make test
```

To run against a different interpreter (e.g. an already-activated environment), override `PYTHON`:

```
make test PYTHON=python
```

On Windows, the virtualenv interpreter lives at `.venv/Scripts/python.exe` rather than `.venv/bin/python` 

### Local development database

Each developer runs their own Postgres in Docker instead of sharing one, so migrations and test data never collide.

```
cp example.env .env
docker compose up -d
python -m userapp.main
```

`docker compose up -d` starts Postgres on `localhost:5434`, migrates it to the checked-out branch's head and seeds admin user 4, the user the UI's dev login token points at. The API serves on port 1111. Run `docker compose up -d` again after switching branches to migrate to the new branch's head.

To start over from an empty database, run `docker compose down -v`, then `docker compose up -d`.

#### Loading a snapshot

Snapshots are `pg_dump -F c` files of a real database. They hold real user data, so get them through the team's approved channel and keep them outside the repo. Point `SNAPSHOT` at the file's absolute path, wherever it is:

```
SNAPSHOT=$HOME/Downloads/dump.dump docker compose run --rm db-restore && docker compose up -d
```

This replaces your local database with the snapshot, then migrates it to your branch's head. The file is never changed, so run it again any time to get back to the same data. The snapshot must come from a database at a revision that exists on `main`, and the local Postgres (17, matching production) must be at least as new as the server it was dumped from.
