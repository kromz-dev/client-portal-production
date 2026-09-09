# Démarrage local

Deux modes :

| Mode | Base | Reverse proxy | Quand |
| --- | --- | --- | --- |
| **A. Docker Compose** *(référence)* | PostgreSQL 16 | Caddy (HTTPS local) | reproduit la prod à l'identique |
| **B. Natif sans Docker** | SQLite (`portail_local.db`) | aucun (Vite ↔ API en direct) | Docker pas installé, itération rapide |

Le mode B fait tourner **le même code applicatif** (API FastAPI + SPA React,
mêmes routes, même auth) ; seuls le moteur de base et le proxy diffèrent.

---

## Mode B — Natif, sans Docker (le plus rapide à lancer)

```bash
# Terminal 1 : API (installe les deps Python dans .local-libs/ au 1er lancement)
./scripts/run-local.sh            # -> http://127.0.0.1:8000  (/docs, /health)

# Terminal 2 : frontend avec rechargement à chaud
make frontend-dev                 # -> http://localhost:5173
```

Ouvrir **http://localhost:5173**, onglet « Créer un compte », puis créer un
projet et déposer un fichier.

Prérequis : `python3` + `pip` (`sudo apt-get install -y python3-pip` si absent)
et `node`/`npm` (déjà présents). Aucun `sudo` sinon.

Remise à zéro : `rm portail_local.db` (la prochaine exécution recrée le schéma).

---

## Mode A — Docker Compose (pile complète, HTTPS local)

Faire tourner toute la pile (React + FastAPI + PostgreSQL + Caddy) en une
commande.

## 1. Prérequis (une seule fois)

Il faut **Docker Engine** + le plugin **docker compose**. Sur Debian / Ubuntu :

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
```

Optionnel mais recommandé — pouvoir lancer `docker` sans `sudo` :

```bash
sudo usermod -aG docker "$USER"
# puis fermer/rouvrir la session (ou : newgrp docker)
```

Optionnel — chiffrer les sauvegardes en local (sinon elles sont écrites en
clair, ce qui est toléré hors production) :

```bash
sudo apt-get install -y age
```

## 2. Configuration

Un fichier `.env` prêt pour le local est **déjà présent** (généré, non
committé). Il contient `ENVIRONMENT=development`, une `SECRET_KEY` aléatoire et
`DOMAIN_NAME=localhost`. Rien à faire.

Pour repartir de zéro : `cp .env.example .env` puis renseigner au minimum
`POSTGRES_PASSWORD` et `SECRET_KEY` (`openssl rand -hex 32`).

## 3. Lancer

```bash
make up        # construit les images et démarre la pile
make ps        # tous les services doivent être "healthy"
make smoke     # vérifie /health
```

Sans `make` :

```bash
docker compose up -d --build
docker compose ps
```

`docker-compose.override.yml` (chargé automatiquement en local) publie l'API
sur `127.0.0.1:8000` et PostgreSQL sur `127.0.0.1:5432` pour le confort de
développement. En production, seul `docker-compose.yml` est utilisé.

## 4. Utiliser

| Adresse | Quoi |
| --- | --- |
| `https://localhost` | le portail (certificat local Caddy → accepter l'avertissement du navigateur une fois) |
| `https://localhost/health` | sonde de santé |
| `http://127.0.0.1:8000/docs` | documentation OpenAPI interactive de l'API |
| `http://127.0.0.1:8000/health` | santé de l'API sans passer par Caddy |

Créer un compte depuis la page de connexion (onglet « Créer un compte »), puis
créer un projet et y déposer un fichier.

### Développement frontend avec rechargement à chaud

```bash
make frontend-dev      # http://localhost:5173, proxy /api -> :8000
```

## 5. Commandes courantes

```bash
make logs      # journaux en direct
make restart   # reconstruit + redémarre l'API après une modif backend
make shell-db  # psql dans le conteneur
make backup    # sauvegarde base + uploads dans ./backups/
make restore   # restaure la dernière sauvegarde (interactif)
make down      # arrête la pile (garde les données)
make clean     # arrête ET supprime les volumes (⚠️ données perdues)
```

`make help` liste toutes les cibles.

## Dépannage

| Symptôme | Cause probable / action |
| --- | --- |
| `permission denied` sur `/var/run/docker.sock` | pas dans le groupe `docker` : préfixer par `sudo`, ou faire l'étape 1 optionnelle puis rouvrir la session |
| `backend` reste `unhealthy` / redémarre | `docker compose logs backend` — souvent `.env` incomplet (`SECRET_KEY`, `POSTGRES_PASSWORD`) |
| `caddy` : erreur de certificat dans le navigateur | normal en local (CA interne Caddy). Accepter l'exception, ou `curl -k` |
| Port 80/443 déjà utilisé | un autre service tourne dessus : `sudo ss -tulpn | grep -E ':80|:443'` |
| `make backup` échoue sur `age` | installer `age`, ou laisser `BACKUP_AGE_RECIPIENT` vide dans `.env` (sauvegarde en clair) |
