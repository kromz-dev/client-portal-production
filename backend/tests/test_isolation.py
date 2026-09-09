"""Cloisonnement horizontal : un client ne voit jamais les données d'un autre.

C'est la promesse centrale du produit (« chaque utilisateur n'accède qu'à ses
propres projets et documents, isolation appliquée au niveau de l'API sur chaque
requête »). `test_roles.py` couvre le cloisonnement vertical (client vs
prestataire) ; ce module couvre le cloisonnement entre deux clients.

Deux formes de refus coexistent, et les deux sont correctes :

* **404 « Projet introuvable. »** sur les routes ouvertes aux clients. Le code
  et le message sont identiques à ceux d'une ressource inexistante, afin de ne
  pas divulguer l'existence de la ressource (cf. `_load_project_for_access`).
* **403** sur les routes réservées au prestataire (`get_current_admin`), où le
  contrôle de rôle s'exécute avant toute recherche en base. Un client n'y a
  aucun droit, que la ressource existe ou non.

La propriété de sécurité vérifiée ici n'est donc pas « le code vaut 404 » mais
**« le refus est le même pour la ressource d'autrui et pour une ressource
inexistante »** — c'est elle qui interdit l'énumération.
"""

import pytest

from helpers import fichier, limiteur_desactive, scenario  # noqa: F401

PROJET_INEXISTANT = 999_999

# (méthode, gabarit d'URL, arguments de requête, statut de refus attendu)
# 403 => route réservée au prestataire ; 404 => route ouverte, projet masqué.
ROUTES_PROJET = [
    ("GET", "/api/projects/{p}", {}, 404),
    ("PUT", "/api/projects/{p}", {"json": {"title": "Detourne"}}, 403),
    ("DELETE", "/api/projects/{p}", {}, 403),
    ("POST", "/api/projects/{p}/documents", {"files": fichier("intrus.txt")}, 404),
    ("GET", "/api/projects/{p}/messages", {}, 404),
    ("POST", "/api/projects/{p}/messages", {"json": {"body": "Intrusion"}}, 404),
    ("GET", "/api/projects/{p}/events", {}, 404),
    ("POST", "/api/projects/{p}/milestones", {"json": {"title": "Intrus"}}, 403),
]


def _routes_enfants(scenario):
    """Routes portant en plus un identifiant de document ou de jalon."""
    pb = scenario.pb
    doc = scenario.livrable_bruno["id"]
    jalon = scenario.jalon_bruno["id"]
    return [
        ("GET", f"/api/projects/{pb}/documents/{doc}/download", {}, 404),
        ("DELETE", f"/api/projects/{pb}/documents/{doc}", {}, 404),
        (
            "POST",
            f"/api/projects/{pb}/documents/{doc}/review",
            {"json": {"decision": "approuve"}},
            404,
        ),
        ("PUT", f"/api/projects/{pb}/milestones/{jalon}", {"json": {"title": "X"}}, 403),
        ("DELETE", f"/api/projects/{pb}/milestones/{jalon}", {}, 403),
    ]


# ---------------------------------------------------------------------------
# Lecture : ce qu'Alice voit d'elle-même, et rien de plus
# ---------------------------------------------------------------------------

def test_la_liste_des_projets_ne_contient_que_les_siens(scenario):
    resp = scenario.client.get("/api/projects", headers=scenario.h_alice)
    assert resp.status_code == 200

    identifiants = {projet["id"] for projet in resp.json()}
    assert identifiants == {scenario.pa}
    assert scenario.pb not in identifiants


def test_le_tableau_de_bord_n_agrege_que_ses_propres_donnees(scenario):
    resp = scenario.client.get("/api/dashboard", headers=scenario.h_alice)
    assert resp.status_code == 200

    # Aucune trace du projet ni des contenus de Bruno, quelle que soit la forme
    # exacte de la charge utile.
    corps = resp.text
    assert "Intranet de Bruno" not in corps
    assert "Secret de Bruno" not in corps
    assert "maquette-bruno.pdf" not in corps


def test_alice_ouvre_son_projet_mais_pas_celui_de_bruno(scenario):
    ok = scenario.client.get(f"/api/projects/{scenario.pa}", headers=scenario.h_alice)
    assert ok.status_code == 200
    assert ok.json()["id"] == scenario.pa

    refus = scenario.client.get(f"/api/projects/{scenario.pb}", headers=scenario.h_alice)
    assert refus.status_code == 404


# ---------------------------------------------------------------------------
# Écriture : toutes les routes portant un {project_id} refusent l'intrusion
# ---------------------------------------------------------------------------

def test_aucune_route_du_projet_de_bruno_n_est_accessible_a_alice(scenario):
    """Balaye l'intégralité de la surface d'API portant un {project_id}."""
    echecs = []

    for methode, gabarit, kwargs, attendu in ROUTES_PROJET:
        url = gabarit.format(p=scenario.pb)
        resp = scenario.client.request(methode, url, headers=scenario.h_alice, **kwargs)
        if resp.status_code != attendu:
            echecs.append(f"{methode} {url} -> {resp.status_code} (attendu {attendu})")

    for methode, url, kwargs, attendu in _routes_enfants(scenario):
        resp = scenario.client.request(methode, url, headers=scenario.h_alice, **kwargs)
        if resp.status_code != attendu:
            echecs.append(f"{methode} {url} -> {resp.status_code} (attendu {attendu})")

    assert not echecs, "Routes mal protegees : " + " ; ".join(echecs)


def test_aucune_route_ne_trahit_l_existence_du_projet_de_bruno(scenario):
    """Le refus doit être identique pour la ressource d'autrui et pour une inexistante.

    C'est la propriété qui interdit l'énumération : si le projet de Bruno
    renvoyait 403 là où un projet fantôme renvoie 404, Alice pourrait déduire
    quels identifiants existent.
    """
    fuites = []

    for methode, gabarit, kwargs, _ in ROUTES_PROJET:
        autrui = scenario.client.request(
            methode, gabarit.format(p=scenario.pb), headers=scenario.h_alice, **kwargs
        )
        fantome = scenario.client.request(
            methode,
            gabarit.format(p=PROJET_INEXISTANT),
            headers=scenario.h_alice,
            **kwargs,
        )
        if autrui.status_code != fantome.status_code:
            fuites.append(
                f"{methode} {gabarit}: autrui={autrui.status_code} "
                f"fantome={fantome.status_code}"
            )
        elif autrui.status_code == 404:
            # Même code : le message ne doit pas différer non plus.
            if autrui.json().get("detail") != fantome.json().get("detail"):
                fuites.append(f"{methode} {gabarit}: messages differents")

    assert not fuites, "Divulgation d'existence : " + " ; ".join(fuites)


def test_la_symetrie_est_vraie_dans_l_autre_sens(scenario):
    """Bruno ne doit pas davantage atteindre le projet d'Alice."""
    resp = scenario.client.get(f"/api/projects/{scenario.pa}", headers=scenario.h_bruno)
    assert resp.status_code == 404

    resp = scenario.client.post(
        f"/api/projects/{scenario.pa}/messages",
        json={"body": "Intrusion de Bruno"},
        headers=scenario.h_bruno,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Références croisées : un identifiant valide sous un parent qui ne l'est pas
# ---------------------------------------------------------------------------

def test_alice_ne_peut_pas_greffer_un_document_de_bruno_sur_son_propre_projet(scenario):
    """IDOR classique : parent légitime, enfant appartenant à autrui."""
    doc_bruno = scenario.livrable_bruno["id"]

    resp = scenario.client.get(
        f"/api/projects/{scenario.pa}/documents/{doc_bruno}/download",
        headers=scenario.h_alice,
    )
    assert resp.status_code == 404

    resp = scenario.client.delete(
        f"/api/projects/{scenario.pa}/documents/{doc_bruno}",
        headers=scenario.h_alice,
    )
    assert resp.status_code == 404


def test_alice_ne_peut_pas_toucher_un_jalon_via_son_propre_projet(scenario):
    """Les jalons sont en écriture réservée au prestataire : refus systématique."""
    jalon_bruno = scenario.jalon_bruno["id"]

    resp = scenario.client.put(
        f"/api/projects/{scenario.pa}/milestones/{jalon_bruno}",
        json={"title": "Detourne"},
        headers=scenario.h_alice,
    )
    assert resp.status_code == 403

    resp = scenario.client.delete(
        f"/api/projects/{scenario.pa}/milestones/{jalon_bruno}",
        headers=scenario.h_alice,
    )
    assert resp.status_code == 403

    # Le jalon de Bruno est bien resté intact.
    projet = scenario.client.get(
        f"/api/projects/{scenario.pb}", headers=scenario.h_admin
    ).json()
    assert [j["title"] for j in projet["milestones"]] == ["Cadrage Bruno"]


# ---------------------------------------------------------------------------
# Non-destruction : un refus ne doit rien avoir modifié
# ---------------------------------------------------------------------------

def test_les_tentatives_d_alice_laissent_le_projet_de_bruno_intact(scenario):
    """Après le balayage complet, Bruno retrouve ses données inchangées."""
    for methode, gabarit, kwargs, _ in ROUTES_PROJET:
        scenario.client.request(
            methode, gabarit.format(p=scenario.pb), headers=scenario.h_alice, **kwargs
        )
    for methode, url, kwargs, _ in _routes_enfants(scenario):
        scenario.client.request(methode, url, headers=scenario.h_alice, **kwargs)

    resp = scenario.client.get(f"/api/projects/{scenario.pb}", headers=scenario.h_bruno)
    assert resp.status_code == 200

    projet = resp.json()
    assert projet["title"] == "Intranet de Bruno"
    assert len(projet["documents"]) == 2
    assert len(projet["milestones"]) == 1

    messages = scenario.client.get(
        f"/api/projects/{scenario.pb}/messages", headers=scenario.h_bruno
    ).json()
    assert [m["body"] for m in messages] == ["Secret de Bruno."]


def test_le_contenu_d_un_message_ne_fuit_jamais_vers_l_autre_client(scenario):
    """Le corps d'un message d'Alice ne doit apparaître dans aucune réponse de Bruno."""
    scenario.client.post(
        f"/api/projects/{scenario.pa}/messages",
        json={"body": "Coordonnees bancaires d'Alice"},
        headers=scenario.h_alice,
    )

    for url in (
        "/api/projects",
        "/api/dashboard",
        f"/api/projects/{scenario.pb}",
        f"/api/projects/{scenario.pb}/messages",
        f"/api/projects/{scenario.pb}/events",
    ):
        resp = scenario.client.get(url, headers=scenario.h_bruno)
        assert resp.status_code == 200, url
        assert "Coordonnees bancaires" not in resp.text, url


# ---------------------------------------------------------------------------
# Contre-épreuves : sans elles, les tests ci-dessus passeraient sur une base vide
# ---------------------------------------------------------------------------

def test_le_prestataire_atteint_les_deux_projets(scenario):
    for projet_id in (scenario.pa, scenario.pb):
        resp = scenario.client.get(
            f"/api/projects/{projet_id}", headers=scenario.h_admin
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == projet_id


def test_chaque_client_accede_bien_a_ses_propres_ressources(scenario):
    """Les refus ci-dessus doivent tenir à l'appartenance, pas à une route cassée."""
    for headers, projet_id, message in (
        (scenario.h_alice, scenario.pa, "Bonjour, une question."),
        (scenario.h_bruno, scenario.pb, "Secret de Bruno."),
    ):
        assert (
            scenario.client.get(
                f"/api/projects/{projet_id}", headers=headers
            ).status_code
            == 200
        )
        corps = [
            m["body"]
            for m in scenario.client.get(
                f"/api/projects/{projet_id}/messages", headers=headers
            ).json()
        ]
        assert corps == [message]


@pytest.mark.parametrize("champ", ["client_id", "owner_id", "user_id"])
def test_alice_ne_peut_pas_se_reattribuer_le_projet_de_bruno(scenario, champ):
    """Réassignation par le corps de la requête : refusée au stade du rôle."""
    resp = scenario.client.put(
        f"/api/projects/{scenario.pb}",
        json={"title": "Intranet de Bruno", champ: scenario.alice_id},
        headers=scenario.h_alice,
    )
    assert resp.status_code == 403

    # Le projet reste bien à Bruno.
    verif = scenario.client.get(
        f"/api/projects/{scenario.pb}", headers=scenario.h_admin
    ).json()
    assert verif["client_id"] == scenario.bruno_id
