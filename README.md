# client-portal-production

Portail client auto-hébergé, prêt pour la production : React + FastAPI +
PostgreSQL, orchestré par Docker Compose, derrière Caddy (HTTPS automatique),
avec sauvegardes chiffrées et procédure de restauration testée.

Un utilisateur se connecte, voit ses projets et leurs statuts, et dépose /
télécharge les documents associés.

## Démarrage

- **En local avec Docker :** `make up` (pile complète, HTTPS local). Voir [`QUICKSTART.md`](QUICKSTART.md).
- **En local sans Docker :** `./scripts/run-local.sh` + `make frontend-dev` (base SQLite, itération rapide).
- **Exploitation / production :** voir [`RUNBOOK.md`](RUNBOOK.md).

## Pile

| Couche | Techno |
| --- | --- |
| Frontend | React 18 (build statique Vite), servi par Nginx |
| API | FastAPI (Python 3.11), Uvicorn, migrations Alembic |
| Base | PostgreSQL 16, isolée sur un réseau Docker interne |
| Reverse proxy | Caddy 2 (TLS Let's Encrypt / certificat local) |
| Sauvegardes | `pg_dump -Fc` + archive uploads, chiffrées `age`, timer systemd |

## Structure

```
backend/            API FastAPI, modèles SQLAlchemy, migrations Alembic
frontend/           SPA React + Dockerfile (build -> Nginx)
scripts/            install, backup, restore, mesures, check_cgnat
deploy/systemd/     unités de démarrage et de sauvegarde
docker-compose.yml           pile de production
docker-compose.override.yml  surcouche de développement local
Caddyfile                    reverse proxy + en-têtes de sécurité
```
