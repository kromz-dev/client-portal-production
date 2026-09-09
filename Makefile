# =============================================================================
# Makefile - raccourcis d'exploitation locale du Portail Client
# =============================================================================
# `make help` pour la liste. Toutes les cibles supposent Docker + le plugin
# `docker compose` installes et le demon accessible (utilisateur dans le groupe
# `docker`, sinon prefixer par `sudo`).
# =============================================================================

SHELL := /bin/bash
COMPOSE := docker compose
DOMAIN ?= localhost

.DEFAULT_GOAL := help

.PHONY: help
help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: check
check: ## Verifie que Docker et Compose sont disponibles
	@command -v docker >/dev/null || { echo "Docker absent. Voir QUICKSTART.md"; exit 1; }
	@$(COMPOSE) version >/dev/null || { echo "Plugin 'docker compose' absent."; exit 1; }
	@test -f .env || { echo ".env absent : cp .env.example .env"; exit 1; }
	@echo "OK : docker, compose et .env presents."

.PHONY: up
up: check ## Construit et demarre toute la pile en arriere-plan
	$(COMPOSE) up -d --build
	@$(MAKE) --no-print-directory ps

.PHONY: down
down: ## Arrete la pile (conteneurs + reseau), conserve les volumes
	$(COMPOSE) down

.PHONY: restart
restart: ## Redemarre le backend seul (rechargement du code apres build)
	$(COMPOSE) up -d --build backend

.PHONY: ps
ps: ## Etat des conteneurs
	$(COMPOSE) ps

.PHONY: logs
logs: ## Suit les journaux de tous les services (Ctrl+C pour quitter)
	$(COMPOSE) logs -f --tail 100

.PHONY: smoke
smoke: ## Teste /health a travers Caddy et en direct sur l'API
	@echo "-- API directe (http://127.0.0.1:8000/health) --"
	@curl -fsS http://127.0.0.1:8000/health && echo
	@echo "-- via Caddy (https://$(DOMAIN)/health, -k = certificat local) --"
	@curl -fsSk https://$(DOMAIN)/health && echo

.PHONY: shell-api
shell-api: ## Ouvre un shell dans le conteneur backend
	$(COMPOSE) exec backend sh

.PHONY: shell-db
shell-db: ## Ouvre psql dans le conteneur de base de donnees
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-portail} -d $${POSTGRES_DB:-portail_client}

.PHONY: migrate
migrate: ## Applique les migrations Alembic (normalement fait au demarrage)
	$(COMPOSE) exec backend alembic upgrade head

.PHONY: backup
backup: ## Sauvegarde base + uploads dans ./backups (non chiffree en local)
	./scripts/backup.sh

.PHONY: restore
restore: ## Restaure la derniere sauvegarde (interactif)
	./scripts/restore.sh

.PHONY: mesures
mesures: ## Releve les metriques SLA reelles (semi-destructif, cf. en-tete du script)
	./scripts/mesures.sh

.PHONY: clean
clean: ## Arrete la pile ET supprime les volumes (DONNEES PERDUES)
	$(COMPOSE) down -v

.PHONY: frontend-dev
frontend-dev: ## Serveur Vite avec rechargement a chaud (http://localhost:5173)
	cd frontend && npm install && npm run dev

# --- Mode natif sans Docker (base SQLite) ------------------------------------

.PHONY: api-local
api-local: ## Lance l'API SANS Docker (SQLite) sur http://127.0.0.1:8000
	./scripts/run-local.sh

.PHONY: test
test: ## Lance la suite de tests backend (pytest, base SQLite temporaire)
	PYTHONPATH=.local-libs python3 -m pytest backend/tests -q

.PHONY: stop-local
stop-local: ## Arrete les serveurs de dev natifs (uvicorn + vite)
	-pkill -f "uvicorn main:app" 2>/dev/null || true
	-pkill -f "vite" 2>/dev/null || true
	@echo "Serveurs de dev natifs arretes."
