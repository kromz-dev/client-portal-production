"""Séparation des rôles : ce qu'un `client` ne peut pas faire, et ce que voit l'`admin`.

Le prestataire est le compte `role == "admin"`. La dépendance `get_current_admin`
(backend/auth.py) renvoie 403 « Accès réservé au prestataire. » pour tout autre rôle.
"""

import pytest

from conftest import login, make_user
from helpers import MDP, fichier, limiteur_desactive, scenario  # noqa: F401

# Routes protégées par `get_current_admin` : un client doit y être refusé en 403.
ROUTES_RESERVEES_AU_PRESTATAIRE = [
    ("GET", "/api/clients", None),
    ("POST", "/api/clients", {"email": "x@exemple.fr", "full_name": "X", "password": MDP}),
    ("POST", "/api/projects", {"title": "Projet pirate", "client_id": 1}),
    ("PUT", "/api/projects/{pa}", {"title": "Titre détourné"}),
    ("DELETE", "/api/projects/{pa}", None),
    ("POST", "/api/projects/{pa}/milestones", {"title": "Jalon pirate"}),
    ("PUT", "/api/projects/{pa}/milestones/{ja}", {"status": "fait"}),
    ("DELETE", "/api/projects/{pa}/milestones/{ja}", None),
]


# ==============================================================================
# Un client est refusé sur les routes du prestataire
# ==============================================================================

@pytest.mark.parametrize("methode,gabarit,corps", ROUTES_RESERVEES_AU_PRESTATAIRE)
def test_un_client_est_refuse_sur_les_routes_du_prestataire(
    client, scenario, methode, gabarit, corps
):
    """Même sur SES PROPRES ressources, un client n'a pas les droits prestataire."""
    url = gabarit.format(pa=scenario.pa, ja=scenario.jalon_alice["id"])
    reponse = client.request(methode, url, headers=scenario.h_alice, json=corps)
    assert reponse.status_code == 403, f"{methode} {url} devrait être interdit au client"
    assert reponse.json()["detail"] == "Accès réservé au prestataire."


@pytest.mark.parametrize("methode,gabarit,corps", ROUTES_RESERVEES_AU_PRESTATAIRE)
def test_le_prestataire_accede_aux_routes_qui_lui_sont_reservees(
    client, scenario, methode, gabarit, corps
):
    """Contrôle miroir : les mêmes appels aboutissent pour l'admin."""
    if corps and corps.get("client_id") == 1:
        corps = dict(corps, client_id=scenario.alice_id)
    url = gabarit.format(pa=scenario.pa, ja=scenario.jalon_alice["id"])
    reponse = client.request(methode, url, headers=scenario.h_admin, json=corps)
    assert reponse.status_code in (200, 201), reponse.text


# ==============================================================================
# Gestion des comptes clients (GET/POST /api/clients)
# ==============================================================================

def test_le_prestataire_liste_les_clients_avec_leur_nombre_de_projets(client, scenario):
    reponse = client.get("/api/clients", headers=scenario.h_admin)
    assert reponse.status_code == 200
    par_email = {c["email"]: c for c in reponse.json()}
    assert set(par_email) == {"alice@exemple.fr", "bruno@exemple.fr"}
    assert par_email["alice@exemple.fr"]["project_count"] == 1
    assert par_email["bruno@exemple.fr"]["project_count"] == 1


def test_la_liste_des_clients_exclut_les_comptes_prestataire(client, scenario):
    emails = [c["email"] for c in client.get("/api/clients", headers=scenario.h_admin).json()]
    assert "presta@exemple.fr" not in emails


def test_la_liste_des_clients_ne_divulgue_aucun_mot_de_passe(client, scenario):
    for entree in client.get("/api/clients", headers=scenario.h_admin).json():
        assert "hashed_password" not in entree
        assert "password" not in entree


def test_le_prestataire_cree_un_client_utilisable_immediatement(db, client, scenario):
    reponse = client.post(
        "/api/clients",
        json={"email": "  Carine@Exemple.FR ", "full_name": "  Carine Dubois  ", "password": MDP},
        headers=scenario.h_admin,
    )
    assert reponse.status_code == 201
    cree = reponse.json()
    assert cree["email"] == "carine@exemple.fr"  # normalisé
    assert cree["full_name"] == "Carine Dubois"  # nettoyé
    assert "hashed_password" not in cree

    # Le compte créé peut se connecter et est bien un `client`.
    entetes = login(client, "carine@exemple.fr")
    assert client.get("/api/auth/me", headers=entetes).json()["role"] == "client"


def test_la_creation_d_un_client_refuse_un_email_deja_pris(client, scenario):
    reponse = client.post(
        "/api/clients",
        json={"email": "alice@exemple.fr", "full_name": "Sosie", "password": MDP},
        headers=scenario.h_admin,
    )
    assert reponse.status_code == 400
    assert "existe déjà" in reponse.json()["detail"]


def test_la_creation_d_un_client_refuse_un_mot_de_passe_trop_court(client, scenario):
    reponse = client.post(
        "/api/clients",
        json={"email": "carine@exemple.fr", "full_name": "Carine", "password": "court"},
        headers=scenario.h_admin,
    )
    assert reponse.status_code == 422


def test_un_client_ne_peut_pas_se_creer_de_compte_prestataire(client, scenario):
    """La route /api/clients est fermée aux clients, et ne crée que des `client`."""
    assert client.post(
        "/api/clients",
        json={"email": "moi-admin@exemple.fr", "full_name": "Moi", "password": MDP},
        headers=scenario.h_alice,
    ).status_code == 403

    # Même le prestataire ne peut pas fabriquer un admin par cette route :
    # le champ `role` n'est pas exposé et est forcé à "client".
    client.post(
        "/api/clients",
        json={"email": "carine@exemple.fr", "full_name": "C", "password": MDP, "role": "admin"},
        headers=scenario.h_admin,
    )
    entetes = login(client, "carine@exemple.fr")
    assert client.get("/api/auth/me", headers=entetes).json()["role"] == "client"
    assert client.get("/api/clients", headers=entetes).status_code == 403


# ==============================================================================
# Portée du prestataire sur les routes projet
# ==============================================================================

def test_le_prestataire_voit_tous_les_projets_tous_clients_confondus(client, scenario):
    """Comportement constaté dans list_projects : pas de filtre pour l'admin."""
    ids = [p["id"] for p in client.get("/api/projects", headers=scenario.h_admin).json()]
    assert set(ids) == {scenario.pa, scenario.pb}


@pytest.mark.parametrize("cle", ["pa", "pb"])
def test_le_prestataire_ouvre_le_projet_de_n_importe_quel_client(client, scenario, cle):
    projet_id = getattr(scenario, cle)
    reponse = client.get(f"/api/projects/{projet_id}", headers=scenario.h_admin)
    assert reponse.status_code == 200
    assert reponse.json()["id"] == projet_id


def test_le_prestataire_lit_les_messages_et_evenements_de_tous_les_projets(client, scenario):
    for projet_id in (scenario.pa, scenario.pb):
        assert client.get(
            f"/api/projects/{projet_id}/messages", headers=scenario.h_admin
        ).status_code == 200
        assert client.get(
            f"/api/projects/{projet_id}/events", headers=scenario.h_admin
        ).status_code == 200


# ==============================================================================
# Revue d'un livrable : réservée au client (miroir des routes admin)
# ==============================================================================

def test_le_prestataire_ne_peut_pas_revoir_son_propre_livrable(client, scenario):
    reponse = client.post(
        f"/api/projects/{scenario.pa}/documents/{scenario.livrable_alice['id']}/review",
        json={"decision": "approuve"},
        headers=scenario.h_admin,
    )
    assert reponse.status_code == 403
    assert reponse.json()["detail"] == "La revue d'un livrable est réservée au client."


def test_le_client_revoit_le_livrable_de_son_propre_projet(client, scenario):
    reponse = client.post(
        f"/api/projects/{scenario.pa}/documents/{scenario.livrable_alice['id']}/review",
        json={"decision": "approuve", "comment": "  Parfait  "},
        headers=scenario.h_alice,
    )
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["review_status"] == "approuve"
    assert corps["review_comment"] == "Parfait"
    assert corps["reviewed_at"] is not None


# ==============================================================================
# Le rôle est attribué par le serveur, jamais par le client
# ==============================================================================

def test_le_type_de_document_depend_du_role_et_non_du_client(client, scenario):
    """Le prestataire dépose un « livrable », le client une « piece_client »."""
    assert scenario.livrable_alice["kind"] == "livrable"
    assert scenario.piece_alice["kind"] == "piece_client"


def test_un_compte_client_ne_peut_pas_s_attribuer_le_role_admin_par_l_api(db, client):
    """Aucune route n'expose `role` en écriture : le rôle reste « client »."""
    make_user(db, "presta@exemple.fr", role="admin")
    make_user(db, "alice@exemple.fr")
    entetes = login(client, "alice@exemple.fr")

    # Tentative via le changement de mot de passe (champ parasite ignoré).
    client.post(
        "/api/auth/change-password",
        json={"current_password": MDP, "new_password": "nouveaumdp456", "role": "admin"},
        headers=entetes,
    )
    assert client.get("/api/auth/me", headers=entetes).json()["role"] == "client"
    assert client.get("/api/clients", headers=entetes).status_code == 403
