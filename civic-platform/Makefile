# ══════════════════════════════════════════════════════════════════════════════
# Smart Civic Intelligence Platform — Deployment Makefile
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: help dev prod down logs ps build migrate seed clean backup restore \
        shell-api shell-db test cert-init cert-renew

help:
	@echo "Smart Civic Intelligence Platform — available commands:"
	@echo ""
	@echo "  make dev          Start local dev stack (hot reload, exposed ports)"
	@echo "  make prod         Start production stack (edge proxy, TLS, no exposed DB)"
	@echo "  make down         Stop all containers"
	@echo "  make logs         Tail logs for all services"
	@echo "  make ps           Show running containers"
	@echo "  make build        Rebuild all images"
	@echo "  make migrate      Run Alembic migrations against the running DB"
	@echo "  make seed         Load sample data (categories, demo officers)"
	@echo "  make test         Run the backend test suite inside the api container"
	@echo "  make shell-api    Open a bash shell in the api container"
	@echo "  make shell-db     Open a psql shell in the postgres container"
	@echo "  make backup       Dump the database to ./backups/"
	@echo "  make restore      Restore the database from the latest backup"
	@echo "  make cert-init    Obtain initial Let's Encrypt certificates"
	@echo "  make cert-renew   Force certificate renewal"
	@echo "  make clean        Remove containers, networks, and volumes (DESTRUCTIVE)"

dev:
	docker compose --profile dev up --build

prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

build:
	docker compose build --no-cache

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m app.scripts.seed_data

test:
	docker compose exec api pytest tests/ -v --cov=app --cov-report=term-missing

shell-api:
	docker compose exec api /bin/bash

shell-db:
	docker compose exec postgres psql -U $${POSTGRES_USER:-civic} -d $${POSTGRES_DB:-civic_platform}

backup:
	@mkdir -p backups
	docker compose exec -T postgres pg_dump -U $${POSTGRES_USER:-civic} $${POSTGRES_DB:-civic_platform} \
		| gzip > backups/civic_$$(date +%Y%m%d_%H%M%S).sql.gz
	@echo "Backup written to backups/"

restore:
	@latest=$$(ls -t backups/*.sql.gz | head -1); \
	echo "Restoring from $$latest"; \
	gunzip -c $$latest | docker compose exec -T postgres psql -U $${POSTGRES_USER:-civic} -d $${POSTGRES_DB:-civic_platform}

cert-init:
	docker compose run --rm certbot certonly --webroot -w /var/www/certbot \
		-d smartcivic.gov.in -d www.smartcivic.gov.in \
		--email admin@smartcivic.gov.in --agree-tos --no-eff-email

cert-renew:
	docker compose exec certbot certbot renew --webroot -w /var/www/certbot
	docker compose exec edge nginx -s reload

clean:
	docker compose down -v --remove-orphans
	@echo "All containers, networks, and volumes removed."
