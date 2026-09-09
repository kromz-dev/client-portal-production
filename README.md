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

## Architecture (4 conteneurs)

- **`caddy`** (`portail_caddy`) — reverse proxy public sur les ports 80/443,
  TLS automatique (Let's Encrypt / ZeroSSL), en-têtes de sécurité, HTTP/3.
  Route `/api/*` et `/health` vers `backend`, tout le reste vers `web`.
- **`web`** (`portail_web`) — Nginx servant le bundle React/Vite compilé et
  intégré à l'image au moment du build. Port 80, réseau privé uniquement,
  jamais exposé directement.
- **`backend`** (`portail_backend`) — API REST FastAPI (Python 3.11, Uvicorn) ;
  applique les migrations Alembic au démarrage puis sert l'application sur le
  port 8000 (privé).
- **`db`** (`portail_db`) — PostgreSQL 16 Alpine, strictement isolé sur le
  réseau interne `backend_net`, aucun port publié sur l'hôte.

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

## Scripts d'exploitation (`scripts/`)

| Script | Rôle |
| :--- | :--- |
| `install.sh` | Préparation de l'hôte (première exécution) : contrôle des dépendances, création des dossiers, génération de la paire de clés `age` et affichage de la clé publique. Idempotent. Si `age` est absent, le script avertit et s'arrête avant la génération de clé — la pile reste utilisable en local, mais sans sauvegardes chiffrées. |
| `install-timers.sh` | Copie et active les unités systemd (`portail-client.service` au boot, `portail-backup.timer` à 02:00). À lancer en `sudo`. |
| `run-local.sh` | Démarre le backend hors Docker sur une base SQLite, pour itérer vite sans monter la pile complète. À compléter par `make frontend-dev`. |
| `backup.sh` | Sauvegarde : `pg_dump -Fc` + archive `tar.gz` des `uploads/`, rotation selon `BACKUP_RETENTION_DAYS`. Chiffrement `age` dès que `BACKUP_AGE_RECIPIENT` est défini ; **obligatoire en `ENVIRONMENT=production`**, où l'absence de destinataire fait échouer le script plutôt que d'écrire en clair. Hors production, la sauvegarde non chiffrée est tolérée avec avertissement. |
| `restore.sh` | Restauration interactive (plus récente d'abord, confirmation `RESTORE`) : déchiffrement transparent, validation `PGDMP`, `pg_restore --clean --if-exists`, copie de sécurité des uploads, vérification post-restauration. |
| `mesures.sh` | Relevé réel des indicateurs SLA (démarrage à froid/chaud, reprise, durée de restauration, latence HTTP). Semi-destructif : jamais sur une production en service. Écrit dans `docs/mesures/`. |
| `check_cgnat.sh` | Détecte si l'hôte est derrière un CGNAT et conseille entre redirection de ports DuckDNS ou Tailscale Funnel. |

## Secrets requis

Dans `.env` (jamais commité) :

| Variable | Génération / rôle |
| :--- | :--- |
| `SECRET_KEY` | `openssl rand -hex 32` — clé de signature JWT ; en `ENVIRONMENT=production` le backend refuse de démarrer si elle est absente, trop courte (< 32 caractères) ou laissée à la valeur de développement. |
| `POSTGRES_PASSWORD` | `openssl rand -hex 32` — mot de passe PostgreSQL ; requis par `docker compose`. |
| `BOOTSTRAP_ADMIN_EMAIL` | Optionnel — au démarrage, garantit l'existence d'un compte `role=admin` : un compte existant portant cet email est promu administrateur. |
| `BOOTSTRAP_ADMIN_PASSWORD` | Optionnel — fourni avec l'email ci-dessus, permet de **créer** le compte administrateur s'il n'existe pas encore. |

La paire de clés `age` qui chiffre les sauvegardes est générée par
`./scripts/install.sh`. **Copiez `secrets/backup_age.key` hors de la machine :
sans cette identité privée, aucune sauvegarde ne peut être restaurée.**

## Documentation

- [`QUICKSTART.md`](./QUICKSTART.md) — démarrage local, avec ou sans Docker.
- [`RUNBOOK.md`](./RUNBOOK.md) — exploitation, incidents, sauvegarde et reprise d'activité, migrations.
- [`ETUDE_DE_CAS.md`](./ETUDE_DE_CAS.md) — contexte, solution et bénéfices de la prestation.
