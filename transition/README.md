The files in this directory were created to facilitate the transition from Mysql to Postgresql.

```shell
docker build -t hub.opensciencegrid.org/chtc/userapp-db-mirror:latest -f ./transition/Dockerfile .
```

```shell
docker build --platform linux/amd64 -t hub.opensciencegrid.org/chtc/userapp-db-mirror:latest -f ./transition/Dockerfile .
```

```shell
docker run --env-file transition/.env --network host hub.opensciencegrid.org/chtc/userapp-db-mirror:latest
```

```shell
docker push hub.opensciencegrid.org/chtc/userapp-db-mirror:latest
```