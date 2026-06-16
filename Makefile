PYTHON            ?= .venv/bin/python

DB_HOST       ?= localhost
DB_PORT       ?= 5433
DB_NAME       ?= userapp_test
DB_USER       ?= postgres
DB_PASSWORD   ?= postgres
SECRET_KEY    ?= test-secret-local
TEST_ADMIN_ID ?= 4
export DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD SECRET_KEY TEST_ADMIN_ID

# setup local DB
test:
	-docker rm -f userapp-test-db >/dev/null 2>&1
	docker run -d --name userapp-test-db \
		-e POSTGRES_USER=$(DB_USER) -e POSTGRES_PASSWORD=$(DB_PASSWORD) -e POSTGRES_DB=$(DB_NAME) \
		-p $(DB_PORT):5432 postgres:16 >/dev/null
	@echo "waiting for postgres on :$(DB_PORT)"
	@until docker exec userapp-test-db pg_isready -U $(DB_USER) >/dev/null 2>&1; do sleep 1; done
	@$(MAKE) test-run; status=$$?; docker rm -f userapp-test-db >/dev/null 2>&1 || true; exit $$status

# DB should already be running
test-run:
	$(PYTHON) -m alembic upgrade head
	$(PYTHON) -m pytest -p no:cacheprovider userapp/api/tests

