"""Outillage partagé par les modules de test.

Ce module ne contient aucun test : il fournit
  * la fixture autouse `limiteur_desactive` (neutralise slowapi pendant les
    tests, sans quoi la 6e connexion de la session renverrait 429) ;
  * la fixture `scenario`, qui construit un jeu de données à deux clients
    étanches (Alice et Bruno) plus le prestataire ;
  * quelques raccourcis (`fichier`, `appeler`).

Les fixtures sont importées dans chaque module de test :

    from helpers import limiteur_desactive, scenario  # noqa: F401

Pytest les considère alors comme définies dans le module importateur.
"""

import pytest

import main
from conftest import login, make_user

MDP = "motdepasse123"


# ------------------------------------------------------------------ fixtures ---

@pytest.fixture(autouse=True)
def limiteur_desactive():
    """Désactive la limitation de débit (5 connexions/minute) le temps du test.

    L'état du limiteur est global au processus : on le restaure et on vide son
    stockage en sortie pour ne pas contaminer les tests suivants.
    """
    ancien = main.limiter.enabled
    main.limiter.enabled = False
    main.limiter.reset()
    yield
    main.limiter.enabled = ancien
    main.limiter.reset()


class Scenario:
    """Deux clients disjoints (Alice, Bruno) et le prestataire.

    Chaque client possède un projet garni : un livrable déposé par le
    prestataire, une pièce déposée par le client, un message et un jalon.
    """

    def __init__(self, db, client):
        self.client = client

        admin = make_user(db, "presta@exemple.fr", role="admin", full_name="Prestataire")
        alice = make_user(db, "alice@exemple.fr", full_name="Alice Martin")
        bruno = make_user(db, "bruno@exemple.fr", full_name="Bruno Durand")
        self.admin_id, self.alice_id, self.bruno_id = admin.id, alice.id, bruno.id

        self.h_admin = login(client, "presta@exemple.fr")
        self.h_alice = login(client, "alice@exemple.fr")
        self.h_bruno = login(client, "bruno@exemple.fr")

        self.projet_alice = self._creer_projet("Refonte du site d'Alice", self.alice_id)
        self.projet_bruno = self._creer_projet("Intranet de Bruno", self.bruno_id)
        self.pa = self.projet_alice["id"]
        self.pb = self.projet_bruno["id"]

        self.livrable_alice = self._deposer(self.pa, self.h_admin, "maquette-alice.pdf")
        self.piece_alice = self._deposer(self.pa, self.h_alice, "logo-alice.png")
        self.livrable_bruno = self._deposer(self.pb, self.h_admin, "maquette-bruno.pdf")
        self.piece_bruno = self._deposer(self.pb, self.h_bruno, "logo-bruno.png")

        self.message_alice = self._poster_message(self.pa, self.h_alice, "Bonjour, une question.")
        self.message_bruno = self._poster_message(self.pb, self.h_bruno, "Secret de Bruno.")

        self.jalon_alice = self._creer_jalon(self.pa, "Cadrage Alice")
        self.jalon_bruno = self._creer_jalon(self.pb, "Cadrage Bruno")

    # -- constructeurs internes -------------------------------------------------
    def _creer_projet(self, titre, client_id):
        resp = self.client.post(
            "/api/projects",
            json={"title": titre, "client_id": client_id},
            headers=self.h_admin,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def _deposer(self, projet_id, headers, nom):
        resp = self.client.post(
            f"/api/projects/{projet_id}/documents",
            files=fichier(nom),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def _poster_message(self, projet_id, headers, corps):
        resp = self.client.post(
            f"/api/projects/{projet_id}/messages",
            json={"body": corps},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def _creer_jalon(self, projet_id, titre):
        resp = self.client.post(
            f"/api/projects/{projet_id}/milestones",
            json={"title": titre},
            headers=self.h_admin,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()


@pytest.fixture
def scenario(db, client):
    return Scenario(db, client)


# ------------------------------------------------------------------ raccourcis ---

def fichier(nom="document.txt", contenu=b"contenu de test", type_mime="text/plain"):
    """Construit l'argument `files=` attendu par TestClient pour un envoi."""
    return {"file": (nom, contenu, type_mime)}


def appeler(client, methode, url, headers=None, **kwargs):
    """Envoie une requête HTTP quelconque (utile pour les tests paramétrés)."""
    return client.request(methode, url, headers=headers, **kwargs)
