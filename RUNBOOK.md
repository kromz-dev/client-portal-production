# RUNBOOK D'EXPLOITATION & DE PRODUCTION
## Portail Client — Stack React / FastAPI / PostgreSQL / Caddy

**Projet :** Portail Client Webflow-Backend Extension  
**Auteur :** Solution Architect & Production Engineer  
**Date de révision :** Septembre 2026  
**Cycle de revue :** Trimestriel / Après incident majeur  
**Statut :** Pile fonctionnelle en local — métriques SLA à relever avant mise en production (voir §1.1)  

---

## 1. Vue d'Ensemble du Service & SLA

Ce Runbook fournit toutes les procédures d'exploitation, de maintenance, de diagnostic d'urgence et de reprise après sinistre pour le **Portail Client**.

### 1.1 Objectifs de Niveau de Service (SLA / SLO)

> **⚠️ Mesures en attente.** La colonne « Mesure réelle » n'est PAS encore
> remplie : la pile n'a pas été déployée publiquement ni chronométrée. Lancer
> `./scripts/mesures.sh` sur la machine cible, committer le rapport dans
> `docs/mesures/`, puis reporter les valeurs ci-dessous. Tant que ce n'est pas
> fait, ne pas présenter ces chiffres à un client.

| Métrique | Engagement Opérationnel (Cible) | Mesure Réelle Constatée |
| :--- | :--- | :--- |
| **Disponibilité globale** | 99.9% (max 43 min d'arrêt/mois) | _à mesurer_ |
| **RTO (Recovery Time Objective)** | < 5 minutes | _à mesurer (`mesures.sh` : reprise + restauration)_ |
| **RPO (Recovery Point Objective)** | < 24 heures | Sauvegarde quotidienne à 02:00 (timer `portail-backup.timer`, `Persistent=true`) |
| **Temps de démarrage à froid** | < 60 secondes | _à mesurer (`mesures.sh` : démarrage à froid)_ |
| **Coût d'infrastructure récurrent** | 0,00 € / mois | 0,00 € (Let's Encrypt + DuckDNS/Tailscale + matériel existant) |

---

## 2. Architecture Technique & Composants

L'application repose sur une pile 100% conteneurisée avec isolation réseau et volumes de persistance dédiés.

### 2.1 Schéma d'Architecture de Déploiement

```
                   [ Trafic Client Internet HTTPS :443 ]
                                    │
                                    ▼
                 ┌──────────────────────────────────────┐
                 │        Box Internet / Pare-Feu       │
                 │   Redirection de ports : 80, 443     │
                 │ (Option de repli CGNAT: Tailscale)   │
                 └──────────────────┬───────────────────┘
                                    │
                                    ▼
           ┌──────────────────────────────────────────────────┐
           │        Reverse Proxy Caddy (Conteneur)           │
           │  - Terminaison TLS auto (Let's Encrypt)          │
           │  - Domaine DuckDNS / Domaine personnalisé        │
           │  - Gestion des certificats & headers HSTS        │
           └────────────┬─────────────────────────┬───────────┘
                        │                         │
     Routes statiques   │                         │ Requêtes API
     et bundle React    │                         │ /api/*
                        ▼                         ▼
         ┌─────────────────────────┐   ┌─────────────────────────┐
         │     web-frontend        │   │       api-backend       │
         │  (Nginx / Caddy static) │   │ (Python 3.11 / FastAPI) │
         │   React SPA compilée    │   │  Uvicorn Worker - :8000 │
         └─────────────────────────┘   └────────────┬────────────┘
                                                    │
                                                    │ Réseau interne
                                                    │ Docker (bridge)
                                                    ▼
                                       ┌─────────────────────────┐
                                       │       db-postgres       │
                                       │   PostgreSQL 16 Alpine  │
                                       │   Port interne : 5432   │
                                       │   (Non exposé au web)   │
                                       └────────────┬────────────┘
                                                    │
                                                    ▼
                                       ┌─────────────────────────┐
                                       │   Volume Persistant     │
                                       │     postgres_data       │
                                       │  (Montage local disque) │
                                       └─────────────────────────┘
```

### 2.2 Inventaire des Composants

| Service Docker | Rôle & Technologie | Ports Internes | Exposition Publique | Volume Persistant |
| :--- | :--- | :--- | :--- | :--- |
| `caddy` | Reverse proxy & TLS Let's Encrypt auto, en-têtes de sécurité | 80, 443 | Oui (ports 80/443 hôte) | `caddy_data`, `caddy_config` |
| `web` | SPA React compilée, servie par Nginx 1.27 Alpine | 80 | Non (réseau `frontend_net` uniquement) | — (image immuable) |
| `backend` | API REST FastAPI, Python 3.11, Uvicorn, migrations Alembic au démarrage | 8000 | Non (réseaux `frontend_net` + `backend_net`) | `./uploads` |
| `db` | Base relationnelle PostgreSQL 16 Alpine | 5432 | **Non (strictement isolé sur `backend_net` en `internal: true`)** | `pgdata` |

> En développement local, `docker-compose.override.yml` publie en plus
> `backend` sur `127.0.0.1:8000` et `db` sur `127.0.0.1:5432`. Ce fichier n'est
> pas utilisé en production (la pile y est lancée avec `-f docker-compose.yml`
> explicitement, cf. l'unité `portail-client.service`).

---

## 3. Déploiement Initial & Démarrage en Une Commande

### 3.1 Prérequis Système
- Système d'exploitation : Linux (Debian 12 / Ubuntu 22.04+ recommandé).
- Docker Engine 24.0+ et Docker Compose v2 (plugin `docker compose`).
- `age` (`apt-get install -y age`) pour le chiffrement des sauvegardes.
- Ports 80 et 443 ouverts et routés vers la machine hôte (ou Tailscale Funnel si CGNAT — voir `scripts/check_cgnat.sh`).
- Domaine / sous-domaine DuckDNS pointant vers l'IP publique.
- **Pour un essai purement local :** voir `QUICKSTART.md` (aucun domaine ni port ouvert requis).

### 3.2 Fichier d'Environnement `.env`

Partir de `.env.example` (`cp .env.example .env`) et renseigner toutes les
clés. Champs sensibles à générer, jamais réutiliser les exemples :

```ini
POSTGRES_USER=portail
POSTGRES_PASSWORD=<openssl rand -hex 16>
POSTGRES_DB=portail_client
POSTGRES_HOST=db
POSTGRES_PORT=5432

SECRET_KEY=<openssl rand -hex 32>       # 32 caractères minimum, sinon l'API refuse de démarrer en prod
ENVIRONMENT=production                   # active les validations strictes (clé, DATABASE_URL, CORS sans `*`)
CORS_ORIGINS=https://mon-portail-client.duckdns.org
DOMAIN_NAME=mon-portail-client.duckdns.org
CADDY_EMAIL=admin@exemple.fr             # notifications d'expiration Let's Encrypt

MAX_UPLOAD_BYTES=10485760
ACCESS_TOKEN_EXPIRE_MINUTES=1440
APP_VERSION=1.0.0

BACKUP_RETENTION_DAYS=7
BACKUP_AGE_RECIPIENT=age1...             # clé publique affichée par ./scripts/install.sh
BACKUP_AGE_IDENTITY=/opt/portail_client/secrets/backup_age.key
```

### 3.3 Lancement Complet de la Pile

```bash
cd /opt/portail_client

# Première fois : prépare l'hôte (dépendances, dossiers, clé age de sauvegarde)
./scripts/install.sh

# Démarre la pile (production : -f explicite, ignore docker-compose.override.yml)
docker compose -f docker-compose.yml up -d --build
```

### 3.4 Vérification Immédiate (Smoke Tests)

Exécuter les vérifications suivantes pour attester du succès du déploiement :

```bash
# Vérifier l'état de santé de tous les conteneurs (ils doivent tous afficher 'Up' ou 'healthy')
docker compose ps

# Vérifier la réponse de santé via le reverse proxy
curl -Iv https://mon-portail-client.duckdns.org/health
```

**Sortie attendue :**
```http
HTTP/2 200
content-type: application/json
server: Caddy

{"status":"healthy","database":"connected","version":"1.0.0"}
```

---

## 4. Opérations Courantes d'Exploitation

### 4.1 Consultation des Journaux (Logs)

Tous les conteneurs journalisent sur `stdout`/`stderr`. La consultation s'effectue directement via Docker Compose.

```bash
# Suivre l'ensemble des journaux en temps réel (Ctrl+C pour quitter)
docker compose logs -f

# Suivre spécifiquement les logs de l'API backend avec horodatage
docker compose logs -f --tail 100 -t backend

# Inspecter les requêtes entrantes et les certificats TLS de Caddy
docker compose logs -f --tail 50 caddy

# Vérifier les requêtes et anomalies de la base de données
docker compose logs -f --tail 50 db
```

### 4.2 Redémarrages Contrôlés

En cas de maintenance sans interruption prolongée :

```bash
# Redémarrer un composant individuel sans impacter les autres
docker compose restart backend

# Recharger la configuration Caddy à chaud SANS coupure de connexion TLS
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

### 4.3 Mise à Jour du Code en Production

Procédure de déploiement d'une nouvelle version :

```bash
# 1. Récupérer les dernières modifications
git pull origin main

# 2. Reconstruire et relancer les conteneurs impactés en tâche de fond
docker compose up -d --build backend

# 3. Vérifier que l'API et le reverse proxy répondent instantanément
docker compose ps
curl -I https://mon-portail-client.duckdns.org/health
```

---

## 5. Gestion des Incidents : "Que faire si le service est tombé ?"

### 5.1 Arbre de Décision Rapide (Triage < 2 minutes)

```
[ ALERTE : Le site ne répond pas / Erreur 502 / Connexion refusée ]
                           │
                           ▼
     Tester l'accessibilité externe (4G / curl)
     $ curl -Iv https://mon-portail-client.duckdns.org/health
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
      Code 502 / 503              Connexion Refusée / Timeout
             │                           │
             ▼                           ▼
   [Caddy fonctionne,          [Caddy éteint ou Problème Réseau]
    Backend non joignable]               │
             │                           ▼
             │                 Vérifier Docker & Ports
             │                 $ docker compose ps
             │                 $ ss -tulpn | grep -E '80|443'
             │                           │
             ▼                           ▼
   Vérifier conteneur backend      Conteneur éteint ?
   $ docker compose logs backend   $ docker compose up -d
             │
             ├─> Erreur DB / Crashloop -> Voir Scénario B
             ├─> OOMKilled (Mémoire)   -> Voir Scénario C
             └─> Relance manuelle      -> $ docker compose restart backend
```

### 5.2 Checklist Diagnostique Étape par Étape

1. **Étape 1 : Vérifier l'état d'exécution des conteneurs**
   ```bash
   docker compose ps -a
   ```
   *Analyse :* Si un conteneur affiche `Exited (137)` ou `Restarting (...)`, relever son nom.

2. **Étape 2 : Analyser les 100 dernières lignes de logs du composant défaillant**
   ```bash
   docker compose logs --tail 100 <service_en_erreur>
   ```

3. **Étape 3 : Vérifier l'espace disque disponible**
   Une saturation disque bloque immédiatement PostgreSQL et Docker.
   ```bash
   df -h /
   docker system df
   ```

---

### 5.3 Résolution des Pannes Types

#### Scénario A : Erreur HTTP 502 Bad Gateway
- **Symptôme :** Caddy répond avec un écran 502.
- **Cause :** Le service FastAPI `backend` est éteint ou ne répond plus sur le port 8000.
- **Action de remédiation :**
  ```bash
  # Vérifier pourquoi le backend est tombé
  docker compose logs --tail 50 backend
  # Redémarrer le backend
  docker compose restart backend
  # Vérifier le rétablissement
  curl -I http://localhost:8000/health
  ```

#### Scénario B : Échec de Connexion Base de Données (`connection refused` ou `password authentication failed`)
- **Symptôme :** L'API renvoie des erreurs 500 et les logs indiquent `psycopg2.OperationalError: could not connect to server`.
- **Cause :** Le conteneur `db` est en cours d'initialisation, a crashé, ou les variables de mot de passe ont été altérées.
- **Action de remédiation :**
  ```bash
  # 1. Vérifier si Postgres tourne
  docker compose ps db
  # 2. Inspecter les logs Postgres
  docker compose logs --tail 50 db
  # 3. Vérifier les identifiants dans le fichier .env
  grep POSTGRES /home/Kram/Bureau/portail_client/.env
  # 4. Relancer la base
  docker compose up -d db
  ```

#### Scénario C : Échec du Renouvellement de Certificat SSL / Timeout Let's Encrypt
- **Symptôme :** Avertissement de sécurité navigateur "Certificat invalide ou expiré".
- **Cause :** L'adresse IP publique a changé (box Internet) et DuckDNS n'est pas à jour, ou les ports 80/443 sont bloqués par la box.
- **Action de remédiation :**
  ```bash
  # 1. Vérifier l'IP publique actuelle
  curl -s ifconfig.me
  # 2. Vérifier la résolution DNS de votre domaine
  dig +short mon-portail-client.duckdns.org
  # 3. Si les IP diffèrent : forcer la mise à jour DuckDNS
  curl -s "https://www.duckdns.org/update?domains=mon-portail-client&token=VOTRE_TOKEN_DUCKDNS&ip="
  # 4. Forcer le rechargement Caddy
  docker compose restart caddy
  ```

#### Scénario D : Disque Plein (`No space left on device`)
- **Symptôme :** Docker refuse d'écrire, la base PostgreSQL se met en lecture seule de sécurité.
- **Action de remédiation :**
  ```bash
  # Nettoyer les images et conteneurs orphelins non utilisés
  docker system prune -af --volumes=false
  # Vérifier l'espace libéré
  df -h /
  # Redémarrer les services
  docker compose restart
  ```

---

## 6. Sauvegarde & Plan de Reprise d'Activité (Disaster Recovery)

### 6.1 Stratégie de Sauvegarde
- **Fréquence :** quotidienne à 02:00 (heure locale de l'hôte), via `portail-backup.timer`.
- **Contenu :** dump PostgreSQL au format personnalisé (`pg_dump -Fc`, compressé) **+** archive `tar.gz` du répertoire `uploads/`.
- **Chiffrement :** chaque artefact est chiffré avec `age` (X25519) — clé publique dans `BACKUP_AGE_RECIPIENT`. Aucune sauvegarde en clair ne subsiste. En `ENVIRONMENT != production` sans clé, les archives sont écrites en clair (toléré en local).
- **Emplacement :** `./backups/` (permissions 0700).
- **Rétention :** `BACKUP_RETENTION_DAYS` jours glissants (défaut 7), rotation automatique.

### 6.2 Script de Sauvegarde : `scripts/backup.sh`

Le script est versionné dans le dépôt (ne pas le recopier ici). Il effectue :
dump `-Fc` → validation de l'en-tête `PGDMP` → archive `uploads/` → chiffrement
`age` → vérification de l'en-tête `age-encryption.org/v1` → rotation → rapport
horodaté. Un `trap EXIT` garantit qu'aucun intermédiaire en clair ne survit à
un échec.

```bash
# Sauvegarde manuelle
cd /opt/portail_client && ./scripts/backup.sh          # ou : make backup

# Vérifier le contenu produit
ls -lh backups/
```

### 6.3 Planification (timer systemd)

La planification passe par systemd (et non cron) : `Persistent=true` rattrape
une exécution manquée si l'hôte était éteint à 02:00 — c'est ce qui garantit
réellement le RPO < 24 h.

```bash
# Installer et activer les unités (portail-client.service, portail-backup.{service,timer})
sudo ./scripts/install-timers.sh

# Contrôler
systemctl list-timers portail-backup --all
journalctl -u portail-backup -n 30 --no-pager
```

> Les unités codent en dur `/opt/portail_client`. Si le projet est ailleurs,
> éditer `deploy/systemd/*.service` avant `install-timers.sh`.

---

### 6.4 Procédure de Restauration : `scripts/restore.sh`

> [!CAUTION]
> Cette opération écrase la base en cours (`pg_restore --clean --if-exists`).
> À n'exécuter qu'en cas de sinistre ou d'exercice planifié.

Le script gère la sélection interactive (plus récent d'abord), le
déchiffrement `age` (via `BACKUP_AGE_IDENTITY`), la validation de l'en-tête
`PGDMP`, un garde-fou de confirmation (`RESTORE`), la copie de sécurité des
uploads actuels, puis la vérification post-restauration (`pg_isready` +
comptage de tables + `/health`).

```bash
cd /opt/portail_client

# Restauration guidée (choix du fichier dans backups/)
./scripts/restore.sh                    # ou : make restore

# Non interactif : dernière sauvegarde, sans confirmation
./scripts/restore.sh --force

# Fichier précis
./scripts/restore.sh backups/db_portail_client_20260909_020000.dump.age
```

Prérequis : l'identité privée `age` doit être présente à l'emplacement
`BACKUP_AGE_IDENTITY` (par défaut `secrets/backup_age.key`). **Sans elle,
aucune sauvegarde chiffrée n'est récupérable.**

Vérification finale :

```bash
docker compose logs --tail 20 backend
curl -sk https://$DOMAIN_NAME/health | jq .
```

---

## 7. Tableau de Contrôle des Métriques & Recette

Grille de recette à remplir lors du passage en production. **Statut actuel :
non exécuté** (`docs/mesures/` vide). Lancer `./scripts/mesures.sh`, reboot
volontaire chronométré, et test 4G, puis cocher.

| Test / Scénario | Procédure de Test | Résultat Attendu | Constaté | Statut |
| :--- | :--- | :--- | :--- | :--- |
| **Exposition Publique HTTPS** | Requête 4G externe sur `https://[domaine]` | Certificat valide, HTTP/2 200 | _à faire_ | ☐ |
| **Démarrage à Froid** | `docker compose up -d` sur machine neuve | Tous conteneurs `healthy` | _à faire_ | ☐ |
| **Reboot Hôte Inopiné** | `sudo reboot` sur le serveur | Reprise intégrale sans intervention | _à faire_ | ☐ |
| **Crash Conteneur API** | `docker compose kill backend` | Restart auto (`unless-stopped`) | _à faire_ | ☐ |
| **Sauvegarde Quotidienne** | `./scripts/backup.sh` | Artefacts `.dump.age` + `.tar.gz.age` non vides | _à faire_ | ☐ |
| **Restauration de Secours** | `./scripts/restore.sh --force` | Données intégrales, `/health` OK | _à faire_ | ☐ |
| **Isolation Réseau** | Connexion externe sur le port 5432 | Connexion bloquée / port invisible | _à faire_ | ☐ |

---

*Fin du Runbook Opérationnel.*
