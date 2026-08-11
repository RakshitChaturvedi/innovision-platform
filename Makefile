.PHONY: up up-stubs down logs migrate buckets streams test smoke smoke2 setup setup2 logs-ingestion logs-registry
up:
	docker compose --env-file .env -f infra/docker-compose.yml up -d --build

up-stubs:
	docker compose --env-file .env \
		-f infra/docker-compose.yml \
		-f infra/docker-compose.stubs.yml \
		up -d --build

down:
	docker compose \
		-f infra/docker-compose.yml \
		-f infra/docker-compose.stubs.yml \
		down

logs:
	docker compose --env-file .env -f infra/docker-compose.yml logs -f

migrate:
	alembic -c migrations/alembic.ini upgrade head

buckets:
	python scripts/create_buckets.py

streams:
	python scripts/create_platform_streams.py

test:
	pytest tests/ -v

smoke:
	python scripts/smoke_test_p1.py

smoke2:
	python scripts/smoke_test_phase2.py

setup: 
	$(MAKE) up
	$(MAKE) migrate
	$(MAKE) buckets
	$(MAKE) streams
	@echo "Phase 1 setup complete."
	@echo "Run 'make up-stubs' to start UC stubs."

setup2:
	$(MAKE) up-stubs
	$(MAKE) migrate
	$(MAKE) buckets
	$(MAKE) streams
	@echo "Phase 2 setup complete."
	@echo "Run 'make smoke2' to verify the ingestion pipeline."

logs-ingestion:
	docker compose \
		--env-file .env \
		-f infra/docker-compose.yml \
		logs -f ingestion

logs-registry:
	docker compose \
		--env-file .env \
		-f infra/docker-compose.yml \
		logs -f camera_registry