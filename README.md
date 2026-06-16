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