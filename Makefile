.PHONY: up up-stubs down logs migrate buckets streams test smoke smoke2 setup setup2

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

setup: up migrate buckets streams
	@echo "Phase 1 setup complete. run 'make up-stubs' to add UC stubs."

setup2: up up-stubs migrate buckets streams
	@echo "Phase 2 setup complete. Ingestion + Analytics services running."