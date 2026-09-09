# Portfolio 1 - Mise en prod complète d'une app web

Est. Hrs.: 17
Status: In Progress
Tasks: Session 1 - Tester le CGNAT et exposer une page en HTTPS (https://app.notion.com/p/Session-1-Tester-le-CGNAT-et-exposer-une-page-en-HTTPS-3d66c396d8c081fc89b8db57b9c599d0?pvs=21), Session 2 - Docker Compose complet derriere Caddy (https://app.notion.com/p/Session-2-Docker-Compose-complet-derriere-Caddy-3d66c396d8c0814ab399de104fd19678?pvs=21), Session 3 - Resilience : restart, sauvegardes, test de restauration (https://app.notion.com/p/Session-3-Resilience-restart-sauvegardes-test-de-restauration-3d66c396d8c08139a47bd73562718664?pvs=21), Session 4 - Runbook, video de passation, etude de cas (https://app.notion.com/p/Session-4-Runbook-video-de-passation-etude-de-cas-3d66c396d8c0815c955cee3b737511d6?pvs=21)

**Palier vendu :** Déploiement et mise en prod (1 900 € / 2 500 $)

**Le problème client**

L'agence sait concevoir et livrer une maquette. Elle ne sait pas mettre en production, tenir le HTTPS, gérer les sauvegardes, ni répondre quand ça tombe. Le projet reste bloqué à l'étape « ça marche chez moi ».

**Ce que je construis**

Une application React + FastAPI + PostgreSQL déployée pour de vrai et accessible publiquement : Docker Compose qui lance toute la pile, Caddy en reverse proxy, HTTPS Let's Encrypt via DuckDNS, sauvegardes automatiques de la base avec restauration testée, journalisation. Livrée avec un runbook écrit et une vidéo de passation, comme dans l'offre réelle.

**La preuve à afficher**

L'URL publique en HTTPS qui répond. Le runbook lisible sur GitHub. Une restauration de sauvegarde chronométrée et filmée. C'est la démonstration exacte du palier le plus cher.

**Stack :** React, Python, FastAPI, PostgreSQL, Docker Compose, Caddy, Let's Encrypt, Linux

**Coût :** 0 €, DuckDNS et Let's Encrypt sont gratuits

---

# Cahier des charges

Ce document a deux usages. Il cadre le projet portfolio, et il sert de modèle réutilisable pour tout devis « Déploiement et mise en prod » à 1 900 €. Ce qui est écrit ici est exactement ce qu'un client lira dans sa proposition, donc il est rédigé comme un vrai cahier des charges, pas comme des notes personnelles.

## 1. Objet

Mettre en production une application web complète sur une infrastructure auto-hébergée, accessible publiquement en HTTPS, sauvegardée, redémarrant seule après une coupure, et livrée avec sa documentation d'exploitation.

L'objectif n'est pas de construire une application impressionnante. C'est de démontrer la mise en production. L'application est le prétexte, l'infrastructure est le sujet.

## 2. Contraintes de départ

- Budget : 0 €. Pas de nom de domaine payant, pas de VPS.
- Matériel : le PC Dell, environ 8 Go de RAM. Les NUC ne sont pas concernés par ce projet.
- Le homelab n'est pas encore en service. **Ce projet ne construit pas le homelab complet.** Proxmox, le cluster et l'architecture à quatre nœuds sont un chantier séparé qui prendrait des semaines. Ici : Debian, Docker, et on avance.
- Temps disponible : 15 à 20 h par semaine, en sessions courtes.

## 3. L'application retenue

Un **portail client** minimal : un utilisateur se connecte, voit ses projets, leurs statuts et les documents associés.

Ce choix n'est pas neutre. C'est exactement ce que vendent des agences Webflow comme Superforge et que leur outil ne sait pas faire, faute d'authentification et de base applicative. La démo répond donc directement à un argument de prospection déjà utilisé.

Périmètre fonctionnel volontairement minuscule : inscription et connexion, une liste de projets, un détail de projet, un envoi de fichier. Rien d'autre.

## 4. Périmètre inclus

- Application React servie en statique
- API en Python avec FastAPI
- Base PostgreSQL
- Authentification par session ou jeton, mots de passe hachés
- Docker Compose qui lance toute la pile en une commande
- Caddy en reverse proxy, HTTPS avec certificat renouvelé automatiquement
- Sauvegarde automatique quotidienne de la base, avec rotation
- Procédure de restauration écrite et testée
- Redémarrage automatique des conteneurs après coupure ou reboot
- Endpoint de santé sur l'API
- Runbook d'exploitation
- Vidéo de passation

## 5. Hors périmètre

Écrit noir sur blanc, parce que c'est ce qui empêche un projet de déraper.

- Aucun travail de design ni de direction artistique. Interface fonctionnelle et sobre.
- Pas de supervision ni d'alertes : c'est le projet portfolio 3.
- Pas d'IA : c'est le projet portfolio 2.
- Pas de paiement, pas d'envoi d'emails, pas de multilingue.
- Pas de Proxmox, pas de cluster, pas de haute disponibilité.
- Pas de CI/CD. Le déploiement se fait à la main, et c'est documenté comme tel.

## 6. Exposition publique

Le point le plus risqué du projet, à traiter en premier et non en dernier.

**Chemin principal :** sous-domaine DuckDNS gratuit, redirection des ports 80 et 443 sur la box, certificat Let's Encrypt obtenu par Caddy.

**Repli, à tester avant tout le reste :** si la connexion passe par du CGNAT, ce qui est fréquent chez les opérateurs français, la redirection de ports ne fonctionnera pas et aucune configuration ne le corrigera. Dans ce cas, **Tailscale Funnel** : URL publique en HTTPS, certificat fourni, aucun port ouvert, fonctionne derrière CGNAT.

**Vérification à faire au tout début :** comparer l'adresse IP publique vue depuis l'extérieur avec celle affichée par l'interface de la box. Si elles diffèrent, c'est du CGNAT, et on part directement sur Tailscale Funnel.

## 7. Livrables

1. L'application accessible à une URL publique en HTTPS
2. Le dépôt GitHub avec le `docker-compose.yml`, le `Caddyfile` et le script de sauvegarde
3. Le runbook
4. La vidéo de passation, moins de dix minutes
5. L'étude de cas rédigée, 500 à 800 mots

## 8. Critères de recette

Le projet n'est fini que si les six sont vrais. Pas cinq.

| Critère | Comment je le vérifie |
| --- | --- |
| L'URL répond en HTTPS depuis un réseau extérieur | Depuis un téléphone en 4G, pas depuis le wifi de la maison |
| Le certificat est valide et se renouvelle seul | Vérification de la date d'expiration et des logs Caddy |
| La pile entière se lance en une commande sur une machine vierge | Test réel, pas de mémoire |
| Après un redémarrage complet du serveur, tout revient sans intervention | Reboot volontaire, chronométré |
| Une sauvegarde est restaurée avec succès | Base détruite volontairement, puis restaurée, chronométré |
| Un inconnu peut exploiter le système avec le seul runbook | Relecture à froid le lendemain, sans rien ajouter de mémoire |

## 9. Découpage

Quatre sessions, dans cet ordre. Ne pas commencer une session avant que la précédente soit vraiment finie.

**Session 1, exposition.** Tester le CGNAT, choisir le chemin, faire répondre une simple page « hello » en HTTPS depuis l'extérieur. Rien d'autre. Tant que ça ne marche pas, l'application ne sert à rien.

**Session 2, la pile.** Docker Compose avec Postgres, l'API et le front derrière Caddy. Endpoint de santé. Authentification.

**Session 3, résilience.** Politiques de redémarrage, sauvegarde quotidienne, test de restauration, reboot volontaire.

**Session 4, passation.** Runbook, vidéo, étude de cas.

## 10. Chiffres à relever pendant, pas après

Ce sont eux qui feront l'étude de cas et le prix. Reconstitués une semaine plus tard, ils seront faux.

- Durée entre la commande de lancement et l'application qui répond
- Temps de retour complet après un reboot
- Durée d'une restauration de sauvegarde, du dump à l'application fonctionnelle
- Taille de la sauvegarde et durée de conservation
- Temps total passé, par session

## 11. Risques identifiés

- **CGNAT** : traité en session 1, avec un repli connu.
- **Le Dell tombe en panne.** Le dépôt GitHub et le script de sauvegarde doivent permettre de tout remonter ailleurs. C'est aussi ce qui rend le projet crédible.
- **Dérive de périmètre.** Toute idée qui arrive en cours de route va dans une liste « plus tard », jamais dans le projet en cours. C'est la règle qui protège les trois projets du portfolio.