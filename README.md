### Release

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
