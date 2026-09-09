"""Fixtures de test : application FastAPI sur une base SQLite temporaire.

Les variables d'environnement sont fixées AVANT l'import de `config`/`database`
(qui lisent l'environnement au chargement du module). La base est recréée
entièrement avant chaque test pour garantir l'isolation.
"""

import os
import sys
import tempfile

import pytest

_TMPDIR = tempfile.mkdtemp(prefix="pc_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMPDIR, 'test.db')}"
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"
os.environ["UPLOAD_DIR"] = os.path.join(_TMPDIR, "uploads")
os.environ["CORS_ORIGINS"] = ""
os.environ.pop("BOOTSTRAP_ADMIN_EMAIL", None)
os.environ.pop("BOOTSTRAP_ADMIN_PASSWORD", None)
os.makedirs(os.environ["UPLOAD_DIR"], exist_ok=True)

# Le paquet backend/ doit être importable (import main, database, ...).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402,F401
import models  # noqa: E402,F401
from auth import get_password_hash  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def app_module():
    return main


# ------------------------------------------------------------------ helpers ---

def make_user(db, email, password="motdepasse123", role="client", full_name=None):
    user = models.User(
        email=email,
        hashed_password=get_password_hash(password),
        role=role,
        full_name=full_name or email.split("@")[0],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client, email, password="motdepasse123"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def make_project(client, admin_headers, client_id, title="Projet test", **kwargs):
    payload = {"title": title, "client_id": client_id}
    payload.update(kwargs)
    resp = client.post("/api/projects", json=payload, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()
