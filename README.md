## Release

```shell
docker build --platform linux/amd64 -t hub.opensciencegrid.org/opensciencegrid/chtc-userapp-api:latest .
```

```shell
docker push hub.opensciencegrid.org/opensciencegrid/chtc-userapp-api:latest
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

