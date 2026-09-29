# Helper script for docker compose with stubs
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.stubs.yml $args
