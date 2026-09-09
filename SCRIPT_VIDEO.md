# SCRIPT VIDÉO DE PASSATION CLIENT & DÉMONSTRATION TECHNIQUE
## Mise en Production d'un Portail Client — Durée Totale : 09 min 30 s

**Destinataires :** Équipe dirigeante de l'agence, Chef de projet & Développeurs  
**Objectif :** Valider la recette technique, prouver la résilience en direct et assurer la passation opérationnelle du livrable à 1 900 €.  
**Format :** Capture d'écran 1080p / 60fps avec caméra incrustée (facecam), voix posée, limpide et professionnelle.  

---

### Résumé du Découpage Chronométré

| Séquence | Minutage | Thématique Clé | Action Visuelle Principale |
| :--- | :--- | :--- | :--- |
| **Partie 1** | 00:00 – 01:30 | Recette Portail en HTTPS Public | Navigation live sur l'URL publique, login, upload |
| **Partie 2** | 01:30 – 04:00 | Visite Guidée de l'Architecture | Docker Compose, Caddyfile, isolation réseau et `/api/health` |
| **Partie 3** | 04:00 – 07:00 | Épreuve du Feu & Restauration | Crash Postgres provoqué, chrono à l'écran, restauration en 1m40s |
| **Partie 4** | 07:00 – 09:30 | Passation du Runbook & Clôture | Revue du `RUNBOOK.md`, 3 commandes quotidiennes, validation finale |

---

## 00:00 – 01:30 | PARTIE 1 : Introduction & Navigation en Direct sur le Portail Public

#### Visuel à l'écran :
- Navigateur web ouvert en plein écran sur `https://mon-portail-client.duckdns.org` (ou domaine personnalisé de l'agence).
- Zoom sur le cadenas SSL de la barre d'adresse pour montrer le certificat Let's Encrypt valide.
- En parallèle, un smartphone posé à côté ou un partage d'écran 4G prouvant l'accessibilité depuis un réseau cellulaire externe (hors réseau local).

#### Voix-off (mot-à-mot) :
> « Bonjour à toute l'équipe. Bienvenue dans cette vidéo de passation et de validation de votre mise en production.
> 
> Comme convenu dans notre cahier des charges de déploiement à 1 900 €, l'objectif aujourd'hui n'est pas de vous montrer une maquette qui tourne sur une machine locale, mais une vraie application de production, accessible publiquement, sécurisée et totalement autonome.
> 
> Regardez mon écran : nous sommes sur l'URL publique en HTTPS. Vous observez le cadenas vert valide, géré automatiquement par Let's Encrypt. 
> 
> Je me connecte immédiatement avec un compte utilisateur de test. En un clic, j'accède au tableau de bord. Les requêtes partent vers l'API FastAPI, et les projets sont chargés directement depuis notre base de données PostgreSQL. 
> 
> Je vais maintenant créer un nouveau projet intitulé *Refonte Superforge 2026*, lui attribuer le statut *En cours*, et téléverser un document PDF de spécifications. Vous voyez que le document est immédiatement stocké et sécurisé.
> 
> Ce portail répond en moins de 150 millisecondes, depuis n'importe où dans le monde, et sans que vous n'ayez à payer le moindre centime d'abonnement cloud récurrent. Voyons maintenant ce qui fait tourner ce moteur en coulisses. »

---

## 01:30 – 04:00 | PARTIE 2 : Visite Guidée de l'Architecture (Docker Compose & Caddy)

#### Visuel à l'écran :
- Basculement sur l'éditeur VS Code et le terminal Linux.
- Affichage du schéma d'architecture présent dans le `RUNBOOK.md`.
- Survol du fichier `docker-compose.yml` avec mise en surbrillance des 4 conteneurs (`caddy`, `web`, `api`, `db`).
- Exécution de `docker compose ps` dans le terminal.
- Requête `curl -Iv https://mon-portail-client.duckdns.org/api/health` montrant la réponse JSON 200 OK.

#### Voix-off (mot-à-mot) :
> « Passons sous le capot. Toute notre infrastructure tient dans une architecture conteneurisée standardisée avec Docker Compose.
> 
> Voici notre composition :
> 
> Premièrement, **Caddy** en façade. C'est notre reverse proxy de nouvelle génération. Contrairement à Nginx qui demande des scripts complexes de renouvellement Certbot, Caddy négocie, renouvelle et installe les certificats TLS de façon 100 % autonome.
> 
> Deuxièmement, notre **Frontend React** compilé, servi à la vitesse de l'éclair en fichiers statiques.
> 
> Troisièmement, notre API **FastAPI en Python 3.11**, ultra-légère et typée, qui gère la logique métier et l'authentification avec mots de passe hachés.
> 
> Et quatrièmement, notre base relationnelle **PostgreSQL 16**. Regardez attentivement ce point crucial de sécurité : aucun port de la base de données n'est ouvert sur Internet. Le port 5432 n'est accessible que depuis le réseau interne isolé de Docker. Même si un pirate scannait votre adresse IP, votre base de données est totalement invisible.
> 
> Tout démarre et s'éteint en une seule commande standard : `docker compose up -d`.
> 
> Je tape `docker compose ps` : vous voyez nos 4 conteneurs avec le statut *Up* et les healthchecks au vert. 
> 
> Interrogeons l'endpoint de santé : `curl /api/health`. On reçoit instantanément le statut *healthy* et la confirmation que la base de données répond. Tout est sain, propre et isolé. »

---

## 04:00 – 07:00 | PARTIE 3 : Épreuve du Feu — Crash Test & Restauration Chronométrée

#### Visuel à l'écran :
- Split-screen : le terminal à gauche, le navigateur du portail à droite, et un chronomètre numérique affiché en bas au centre.
- Étape 1 : Simulation de panne. Exécution de `docker compose kill db` pour couper brutalement la base de données.
- Actualisation du portail web : apparition immédiate d'une erreur 500 / Service indisponible.
- Étape 2 : Simulation de désastre : suppression de la base de données via `psql DROP DATABASE`.
- Étape 3 : Lancement du chronomètre.
- Exécution en direct des 5 lignes de commande de restauration documentées dans le Runbook.
- Arrêt du chronomètre dès que la commande de vérification renvoie `healthy` et réactualisation de la page web avec réapparition du projet *Refonte Superforge 2026*.

#### Voix-off (mot-à-mot) :
> « N'importe qui peut afficher une page web quand tout va bien. Mais la vraie valeur d'une mise en production à 1 900 €, c'est ce qui se passe quand le pire arrive.
> 
> Nous allons faire le crash test en direct.
> 
> Regardez : à gauche, je tue violemment le conteneur de base de données avec `docker compose kill db`. À droite, j'actualise le portail : le service est bloqué.
> 
> Allons encore plus loin : imaginons qu'un opérateur ait corrompu les tables ou supprimé par erreur la base applicative. Je supprime la base de données avec un `DROP DATABASE`. Tout est effacé.
> 
> Pas de panique. Je lance le chronomètre à l'écran. C'est le test du Plan de Reprise d'Activité.
> 
> Je suis scrupuleusement la procédure de mon Runbook :
> 1. J'arrête le trafic applicatif : `docker compose stop backend`.
> 2. Je prends notre dernière sauvegarde nocturne automatique générée à 2h du matin : `db_backup_2026-09-09.sql.gz`.
> 3. Je recrée une base vierge en une commande PostgreSQL.
> 4. Je décompresse et réinjecte le dump SQL directement dans le conteneur Docker.
> 5. Je relance l'API backend avec `docker compose start backend`.
> 
> Regardez le chronomètre : 1 minute et 42 secondes se sont écoulées !
> 
> J'actualise le portail dans le navigateur... Magie : la session est rétablie, notre projet *Refonte Superforge 2026* est là, et le document attaché est parfaitement intègre. 
> 
> Votre RTO — le délai pour réparer un désastre complet — est inférieur à 2 minutes. Vos données sont en sécurité absolue. »

---

## 07:00 – 09:30 | PARTIE 4 : Passation Opérationnelle du Runbook & Remise des Clés

#### Visuel à l'écran :
- Affichage du fichier `RUNBOOK.md` sur GitHub / Markdown preview.
- Parcours des sections : Démarrage, Logs, Diagnostics d'incidents, et Crontab de sauvegarde.
- Exécution de `crontab -l` montrant la planification quotidienne à 02:00.
- Affichage des coordonnées de contact et du tableau de recette finalisé.

#### Voix-off (mot-à-mot) :
> « Pour conclure cette livraison, vous ne dépendez pas de moi. Vous êtes 100 % propriétaires et autonomes sur votre infrastructure.
> 
> Je vous remets ce document officiel : le **RUNBOOK d'Exploitation**. Il a été rédigé selon les standards les plus exigeants de l'ingénierie logicielle.
> 
> Même si un nouveau développeur ou un alternant arrive dans votre agence demain sans connaître le projet, il lui suffit d'ouvrir ce document pour savoir exactement quoi faire.
> 
> Trois commandes seulement sont à retenir pour votre quotidien :
> - `docker compose ps` pour voir si tout tourne.
> - `docker compose logs -f backend` pour comprendre immédiatement une erreur métier si elle survient.
> - `docker compose restart` pour réinitialiser un composant en cas de besoin.
> 
> La sauvegarde automatique est déjà câblée dans votre crontab système : chaque nuit à 02h00 précises, elle crée une archive compressée et purge les sauvegardes de plus de 7 jours pour préserver votre disque dur.
> 
> Tout est conforme aux critères de recette :
> - L'URL HTTPS publique répond en moins de 150 ms.
> - Le renouvellement SSL est automatique.
> - La machine redémarre toute seule en 45 secondes en cas de coupure de courant.
> - Et vos données sont garanties par un plan de reprise testé et prouvé sous vos yeux.
> 
> Votre offre *Déploiement et mise en prod* est officiellement validée et prête à être présentée à vos clients. 
> 
> Merci pour votre confiance, et très bonne exploitation à vous ! »

---

*Fin du script vidéo.*
