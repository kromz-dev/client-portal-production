"""Authentification : jetons, connexion, identité et changement de mot de passe.

Couvre POST /api/auth/login, POST /api/auth/token, GET /api/auth/me,
POST /api/auth/change-password, ainsi que les sondes de santé.
"""

import pytest

import main
from conftest import login, make_user
from helpers import MDP, limiteur_desactive  # noqa: F401  (fixture autouse)

# Toutes les routes métier, pour vérifier qu'aucune n'est ouverte sans jeton.
ROUTES_PROTEGEES = [
    ("GET", "/api/auth/me"),
    ("GET", "/api/clients"),
    ("POST", "/api/clients"),
    ("GET", "/api/projects"),
    ("POST", "/api/projects"),
    ("GET", "/api/projects/1"),
    ("PUT", "/api/projects/1"),
    ("DELETE", "/api/projects/1"),
    ("POST", "/api/projects/1/documents"),
    ("GET", "/api/projects/1/documents/1/download"),
    ("DELETE", "/api/projects/1/documents/1"),
    ("POST", "/api/projects/1/documents/1/review"),
    ("GET", "/api/projects/1/messages"),
    ("POST", "/api/projects/1/messages"),
    ("GET", "/api/projects/1/events"),
    ("POST", "/api/projects/1/milestones"),
    ("PUT", "/api/projects/1/milestones/1"),
    ("DELETE", "/api/projects/1/milestones/1"),
    ("GET", "/api/dashboard"),
]


# ==============================================================================
# Sondes de santé (publiques par conception)
# ==============================================================================

@pytest.mark.parametrize("url", ["/health", "/api/health"])
def test_la_sonde_de_sante_repond_sans_authentification(client, url):
    reponse = client.get(url)
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["status"] == "healthy"
    assert corps["database"] == "connected"
    assert "version" in corps


# ==============================================================================
# Accès sans jeton / avec un jeton invalide
# ==============================================================================

@pytest.mark.parametrize("methode,url", ROUTES_PROTEGEES)
def test_toute_route_metier_refuse_l_acces_sans_jeton(client, methode, url):
    reponse = client.request(methode, url)
    assert reponse.status_code == 401, f"{methode} {url} n'exige pas de jeton"


@pytest.mark.parametrize(
    "entete",
    [
        {"Authorization": "Bearer jeton.invalide.xxx"},
        {"Authorization": "Bearer "},
        {"Authorization": "eyJhbGciOiJIUzI1NiJ9.e30.signature"},  # schéma absent
        {"Authorization": "Basic YWRtaW46YWRtaW4="},  # mauvais schéma
        {"Authorization": "Bearer"},
    ],
)
def test_un_entete_authorization_malforme_est_refuse(db, client, entete):
    make_user(db, "alice@exemple.fr")
    assert client.get("/api/auth/me", headers=entete).status_code == 401


def test_un_jeton_signe_avec_une_autre_cle_est_refuse(db, client):
    """Un jeton bien formé mais signé avec une autre clé ne doit pas passer."""
    from jose import jwt

    make_user(db, "alice@exemple.fr")
    faux_jeton = jwt.encode(
        {"sub": "alice@exemple.fr"}, "une-autre-cle-totalement-differente", algorithm="HS256"
    )
    reponse = client.get("/api/auth/me", headers={"Authorization": f"Bearer {faux_jeton}"})
    assert reponse.status_code == 401


def test_un_jeton_valide_dont_le_compte_a_disparu_est_refuse(db, client):
    """Le compte est supprimé après l'émission du jeton : l'accès doit tomber."""
    import models

    utilisateur = make_user(db, "ephemere@exemple.fr")
    entetes = login(client, "ephemere@exemple.fr")
    db.query(models.User).filter(models.User.id == utilisateur.id).delete()
    db.commit()
    assert client.get("/api/auth/me", headers=entetes).status_code == 401


def test_un_jeton_expire_est_refuse(db, client):
    from datetime import timedelta

    from auth import create_access_token

    make_user(db, "alice@exemple.fr")
    jeton = create_access_token(
        {"sub": "alice@exemple.fr"}, expires_delta=timedelta(minutes=-5)
    )
    reponse = client.get("/api/auth/me", headers={"Authorization": f"Bearer {jeton}"})
    assert reponse.status_code == 401


# ==============================================================================
# Connexion (JSON) — /api/auth/login
# ==============================================================================

def test_la_connexion_avec_les_bons_identifiants_renvoie_un_jeton_exploitable(db, client):
    make_user(db, "alice@exemple.fr")
    reponse = client.post(
        "/api/auth/login", json={"email": "alice@exemple.fr", "password": MDP}
    )
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["token_type"] == "bearer"
    assert corps["access_token"]

    # Le jeton obtenu ouvre bien une route protégée.
    entetes = {"Authorization": f"Bearer {corps['access_token']}"}
    assert client.get("/api/auth/me", headers=entetes).status_code == 200


def test_la_connexion_avec_un_mauvais_mot_de_passe_est_refusee(db, client):
    make_user(db, "alice@exemple.fr")
    reponse = client.post(
        "/api/auth/login", json={"email": "alice@exemple.fr", "password": "mauvais-mdp"}
    )
    assert reponse.status_code == 401
    assert reponse.json()["detail"] == "Email ou mot de passe incorrect."


def test_la_connexion_avec_un_email_inconnu_renvoie_le_meme_message(db, client):
    """Le message ne doit pas permettre de distinguer compte absent et mdp faux."""
    make_user(db, "alice@exemple.fr")
    inconnu = client.post(
        "/api/auth/login", json={"email": "fantome@exemple.fr", "password": MDP}
    )
    mauvais_mdp = client.post(
        "/api/auth/login", json={"email": "alice@exemple.fr", "password": "zzz"}
    )
    assert inconnu.status_code == mauvais_mdp.status_code == 401
    assert inconnu.json()["detail"] == mauvais_mdp.json()["detail"]


def test_la_connexion_normalise_la_casse_et_les_espaces_de_l_email(db, client):
    make_user(db, "alice@exemple.fr")
    reponse = client.post(
        "/api/auth/login", json={"email": "  ALICE@Exemple.FR  ", "password": MDP}
    )
    assert reponse.status_code == 200


def test_la_connexion_refuse_un_corps_incomplet(client):
    assert client.post("/api/auth/login", json={"email": "alice@exemple.fr"}).status_code == 422
    assert client.post("/api/auth/login", json={}).status_code == 422


# ==============================================================================
# Connexion (formulaire OAuth2) — /api/auth/token
# ==============================================================================

def test_la_route_token_accepte_le_formulaire_oauth2(db, client):
    make_user(db, "alice@exemple.fr")
    reponse = client.post(
        "/api/auth/token", data={"username": "alice@exemple.fr", "password": MDP}
    )
    assert reponse.status_code == 200
    entetes = {"Authorization": f"Bearer {reponse.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=entetes).json()["email"] == "alice@exemple.fr"


def test_la_route_token_refuse_un_mauvais_mot_de_passe(db, client):
    make_user(db, "alice@exemple.fr")
    reponse = client.post(
        "/api/auth/token", data={"username": "alice@exemple.fr", "password": "zzz"}
    )
    assert reponse.status_code == 401


# ==============================================================================
# Identité courante — /api/auth/me
# ==============================================================================

def test_me_renvoie_le_compte_correspondant_au_jeton(db, client):
    make_user(db, "alice@exemple.fr", full_name="Alice Martin")
    make_user(db, "presta@exemple.fr", role="admin", full_name="Prestataire")

    corps_alice = client.get("/api/auth/me", headers=login(client, "alice@exemple.fr")).json()
    assert corps_alice["email"] == "alice@exemple.fr"
    assert corps_alice["role"] == "client"
    assert corps_alice["full_name"] == "Alice Martin"

    corps_admin = client.get("/api/auth/me", headers=login(client, "presta@exemple.fr")).json()
    assert corps_admin["email"] == "presta@exemple.fr"
    assert corps_admin["role"] == "admin"


def test_me_ne_divulgue_jamais_le_mot_de_passe_hache(db, client):
    make_user(db, "alice@exemple.fr")
    corps = client.get("/api/auth/me", headers=login(client, "alice@exemple.fr")).json()
    assert "hashed_password" not in corps
    assert "password" not in corps


def test_deux_comptes_recoivent_des_jetons_distincts(db, client):
    make_user(db, "alice@exemple.fr")
    make_user(db, "bruno@exemple.fr")
    entetes_alice = login(client, "alice@exemple.fr")
    entetes_bruno = login(client, "bruno@exemple.fr")

    assert entetes_alice != entetes_bruno
    assert client.get("/api/auth/me", headers=entetes_alice).json()["email"] == "alice@exemple.fr"
    assert client.get("/api/auth/me", headers=entetes_bruno).json()["email"] == "bruno@exemple.fr"


# ==============================================================================
# Changement de mot de passe
# ==============================================================================

def test_le_changement_de_mot_de_passe_exige_l_ancien_mot_de_passe(db, client):
    make_user(db, "alice@exemple.fr")
    entetes = login(client, "alice@exemple.fr")
    reponse = client.post(
        "/api/auth/change-password",
        json={"current_password": "pas-le-bon", "new_password": "nouveaumdp456"},
        headers=entetes,
    )
    assert reponse.status_code == 401
    assert reponse.json()["detail"] == "Mot de passe actuel incorrect."
    # L'ancien mot de passe reste valide : rien n'a changé.
    assert client.post(
        "/api/auth/login", json={"email": "alice@exemple.fr", "password": MDP}
    ).status_code == 200


def test_apres_changement_l_ancien_mot_de_passe_ne_fonctionne_plus(db, client):
    make_user(db, "alice@exemple.fr")
    entetes = login(client, "alice@exemple.fr")
    reponse = client.post(
        "/api/auth/change-password",
        json={"current_password": MDP, "new_password": "nouveaumdp456"},
        headers=entetes,
    )
    assert reponse.status_code == 200

    assert client.post(
        "/api/auth/login", json={"email": "alice@exemple.fr", "password": MDP}
    ).status_code == 401
    assert client.post(
        "/api/auth/login", json={"email": "alice@exemple.fr", "password": "nouveaumdp456"}
    ).status_code == 200


def test_le_nouveau_mot_de_passe_doit_respecter_la_longueur_minimale(db, client):
    make_user(db, "alice@exemple.fr")
    entetes = login(client, "alice@exemple.fr")
    reponse = client.post(
        "/api/auth/change-password",
        json={"current_password": MDP, "new_password": "court"},
        headers=entetes,
    )
    assert reponse.status_code == 422


def test_le_changement_de_mot_de_passe_n_affecte_que_le_compte_courant(db, client):
    """Alice change son mot de passe : celui de Bruno reste intact."""
    make_user(db, "alice@exemple.fr")
    make_user(db, "bruno@exemple.fr")
    client.post(
        "/api/auth/change-password",
        json={"current_password": MDP, "new_password": "nouveaumdp456"},
        headers=login(client, "alice@exemple.fr"),
    )
    assert client.post(
        "/api/auth/login", json={"email": "bruno@exemple.fr", "password": MDP}
    ).status_code == 200


def test_le_jeton_emis_avant_le_changement_de_mot_de_passe_reste_valide(db, client):
    """Comportement constaté et documenté, non un test de sécurité.

    Les jetons sont des JWT sans état : il n'existe ni liste de révocation ni
    incrément de version côté compte. Un jeton émis avant le changement de mot
    de passe reste donc utilisable jusqu'à son expiration
    (`ACCESS_TOKEN_EXPIRE_MINUTES`, 1440 min par défaut). Ce test fige ce
    comportement pour qu'une éventuelle révocation future soit un changement
    explicite et visible.
    """
    make_user(db, "alice@exemple.fr")
    ancien_jeton = login(client, "alice@exemple.fr")
    client.post(
        "/api/auth/change-password",
        json={"current_password": MDP, "new_password": "nouveaumdp456"},
        headers=ancien_jeton,
    )
    assert client.get("/api/auth/me", headers=ancien_jeton).status_code == 200


# ==============================================================================
# Limitation de débit sur la connexion
# ==============================================================================

def test_les_tentatives_de_connexion_sont_limitees_en_debit(db, client):
    """5 tentatives par minute et par adresse : la 6e doit renvoyer 429."""
    make_user(db, "alice@exemple.fr")
    main.limiter.reset()
    main.limiter.enabled = True

    codes = [
        client.post(
            "/api/auth/login", json={"email": "alice@exemple.fr", "password": "mauvais"}
        ).status_code
        for _ in range(6)
    ]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
