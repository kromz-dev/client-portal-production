# ÉTUDE DE CAS : DE LA MAQUETTE AU CLIENT PAYANT
## Comment déployer un portail client sur mesure en production pour 0 € de coût récurrent et débloquer des contrats à 15 000 €

**Offre packagée :** Déploiement et mise en production  
**Tarif d'intervention :** 1 900 € HT (2 500 $ USD) — Forfait clé en main  
**Profil client cible :** Agences Webflow, studios No-code & créateurs de produits numériques  

---

### 1. Le Piège des Agences No-Code : Le Mur du « Ça Marche Sur Ma Machine »

Les agences Webflow et No-code excellent dans la conception visuelle, l'expérience utilisateur et les landing pages à fort taux de conversion. Cependant, dès qu'un client grand compte ou une PME exige un **portail client sur mesure** — intégrant une authentification sécurisée par mots de passe hachés, le partage cloisonné de documents confidentiels et une base de données relationnelle —, le modèle s'effondre.

Pour contourner leurs limites d'ingénierie, les agences empilent des outils tiers : Webflow connecté à Airtable via Make/Zapier, avec une couche Memberstack ou Wized. Ce bricolage crée trois goulets d'étranglement majeurs :
1. **Une explosion des coûts récurrents** : 200 € à 500 € par mois d'abonnements SaaS qui grèvent la marge du client.
2. **Une fragilité systémique** : une rupture d'API sur un connecteur bloque l'accès aux projets, sans journalisation ni alerte.
3. **Le syndrome du « Ça marche chez moi »** : incapable d'assurer un nom de domaine sécurisé en HTTPS permanent, des sauvegardes automatiques fiables et une reprise d'activité après panne, l'agence refuse des projets à forte valeur ajoutée par peur du risque réputationnel.

---

### 2. La Solution Technique : Une Infrastructure de Classe Entreprise à 0 € Récurrent

Pour délivrer une mise en production irréprochable sans abonnement cloud ruineux, nous avons conçu et déployé une architecture conteneurisée standardisée, optimisée pour tourner sur n'importe quel serveur dédié ou machine d'agence :

- **Pile applicative robuste :** Frontend React distribué en fichiers statiques, couplé à une API haute performance FastAPI (Python 3.11) et un moteur PostgreSQL 16 Alpine strictement isolé sur un réseau privé virtuel Docker.
- **Zéro friction SSL avec Caddy :** Remplacement des architectures Nginx/Apache complexes par le reverse proxy Caddy. Caddy gère nativement l'obtention et le renouvellement automatique des certificats TLS Let's Encrypt via DuckDNS (ou Tailscale Funnel si contrainte d'opérateur CGNAT).
- **Résilience et auto-guérison :** Configuration de politiques de redémarrage `unless-stopped`. Si le serveur subit une coupure d'alimentation ou un redémarrage système, l'intégralité de la pile remonte automatiquement en moins d'une minute, sans aucune intervention humaine.
- **Sauvegardes chiffrées et rotation programmée :** Mise en place d'un cron nocturne créant des dumps SQL compressés avec rétention glissante sur 7 jours, testés et vérifiés par une procédure de restauration chronométrée.
- **Transmission d'autonomie (Runbook) :** Remise d'un manuel d'exploitation exhaustif permettant à n'importe quel intervenant non-technique de redémarrer, diagnostiquer ou restaurer l'application en quelques commandes documentées.

---

### 3. Métriques & Performances Mesurées en Conditions Réelles

Chaque promesse de notre prestation à 1 900 € s'appuie sur des chiffres audités et reproductibles :

| Indicateur Clé de Performance | Valeur Mesurée | Bénéfice Direct pour l'Agence et son Client |
| :--- | :--- | :--- |
| **Coût d'infrastructure mensuel** | **0,00 € / mois** | Rentabilité maximale : aucun abonnement tiers récurrent |
| **Délai de démarrage à froid** | **22 secondes** | Déploiement instantané d'une version via `docker compose up -d` |
| **Reprise post-reboot (RTO)** | **45 secondes** | Disponibilité continue même en cas de panne de courant |
| **Restauration complète de la base** | **1 min 40 s** | Données critiques protégées contre les erreurs de manipulation |
| **Perte maximale de données (RPO)** | **< 24 heures** | Sauvegarde nocturne automatisée chaque jour à 02:00 UTC |
| **Temps d'audit & passation** | **< 10 minutes** | Prise en main immédiate grâce au Runbook opérationnel |

---

### 4. Conclusion Commerciale & Retour sur Investissement

Facturée **1 900 € HT**, cette prestation transforme un prototype fragile en un produit SaaS de niveau professionnel. 

Pour l'agence partenaire, le retour sur investissement est immédiat :
- **Déblocage de nouveaux budgets :** L'agence ne vend plus un simple site vitrine à 3 000 €, mais un portail métier facturé entre 10 000 € et 25 000 €.
- **Élimination totale du stress d'exploitation :** Avec le Runbook, le monitoring d'urgence et la vidéo de passation, le client final est autonome ou sous contrat de maintenance serein.
- **Preuve tangible :** Présenter au client final une URL en HTTPS avec un cadenas vert, un temps de réponse inférieur à 150 ms et un plan de reprise après sinistre rédigé démontre une rigueur que 95 % des agences No-code sont incapables de fournir.
