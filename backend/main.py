import logging
import os
import uuid
from typing import List

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload

from auth import create_access_token, get_current_user, get_password_hash, verify_password
from config import settings
from database import get_db
from models import Document, Project, User
from schemas import (
    DocumentResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    Token,
    UserLogin,
    UserRegister,
    UserResponse,
)

logger = logging.getLogger("portail_client.main")

UPLOAD_DIR = settings.upload_dir
try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except OSError as exc:
    logger.warning("Impossible de créer le dossier d'uploads %s : %s", UPLOAD_DIR, exc)

# Extensions autorisées pour l'envoi de documents (comparaison insensible à la casse).
ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".txt",
    ".csv",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".odt",
    ".ods",
}

# Taille des blocs lus lors de l'écriture d'un document envoyé (64 Kio).
UPLOAD_CHUNK_SIZE = 64 * 1024


app = FastAPI(
    title="Portail Client API",
    description="API minimale et robuste pour le portail client",
    version=settings.app_version,
)


# ==============================================================================
# Limitation de débit (slowapi)
# ==============================================================================

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Trop de tentatives. Réessayez dans une minute."},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)


# ==============================================================================
# Configuration CORS
# ==============================================================================

_cors_origins = settings.cors_origin_list
if not _cors_origins:
    # Aucune origine déclarée. En production le SPA est servi par Caddy sur le
    # même domaine que l'API : le CORS n'a alors aucune raison d'exister, donc on
    # n'installe pas le middleware du tout (aucune origine tierce autorisée).
    # En développement, le serveur Vite tourne sur un autre port et a besoin
    # d'une autorisation large, mais sans identifiants.
    if settings.environment != "production":
        logger.warning(
            "CORS_ORIGINS est vide : toutes les origines sont autorisées "
            "(mode développement uniquement)."
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
elif "*" in _cors_origins:
    # `*` combiné à des identifiants est invalide et ignoré par les navigateurs.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ==============================================================================
# Health Check
# ==============================================================================

def _health_payload(db: Session):
    """Vérifie la connexion à la base et renvoie le corps de réponse /health."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Échec de la vérification de santé : base de données injoignable")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": "disconnected"},
        )
    return {
        "status": "healthy",
        "database": "connected",
        "version": settings.app_version,
    }


@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    return _health_payload(db)


# ==============================================================================
# Authentication Routes
# ==============================================================================

@app.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Auth"])
@limiter.limit("5/minute")
def register(request: Request, user_in: UserRegister, db: Session = Depends(get_db)):
    normalized_email = user_in.email.strip().lower()
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un compte avec cet email existe déjà.",
        )

    user = User(
        email=normalized_email,
        hashed_password=get_password_hash(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=Token, tags=["Auth"])
@limiter.limit("5/minute")
def login(request: Request, user_in: UserLogin, db: Session = Depends(get_db)):
    normalized_email = user_in.email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.email})
    return Token(access_token=access_token, token_type="bearer")


@app.post("/api/auth/token", response_model=Token, tags=["Auth"])
@limiter.limit("5/minute")
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    normalized_email = form_data.username.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.email})
    return Token(access_token=access_token, token_type="bearer")


@app.get("/api/auth/me", response_model=UserResponse, tags=["Auth"])
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# ==============================================================================
# Projects Routes
# ==============================================================================

@app.get("/api/projects", response_model=List[ProjectResponse], tags=["Projects"])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    projects = (
        db.query(Project)
        .options(selectinload(Project.documents))
        .filter(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return projects


@app.post("/api/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, tags=["Projects"])
def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = Project(
        user_id=current_user.id,
        title=project_in.title.strip(),
        description=project_in.description.strip() if project_in.description else None,
        status=project_in.status if project_in.status else "En cours",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.get("/api/projects/{project_id}", response_model=ProjectResponse, tags=["Projects"])
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projet introuvable.",
        )
    return project


@app.put("/api/projects/{project_id}", response_model=ProjectResponse, tags=["Projects"])
def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projet introuvable.",
        )

    if project_in.title is not None:
        project.title = project_in.title.strip()
    if project_in.description is not None:
        project.description = project_in.description.strip() if project_in.description else None
    if project_in.status is not None:
        project.status = project_in.status

    db.commit()
    db.refresh(project)
    return project


@app.delete("/api/projects/{project_id}", status_code=status.HTTP_200_OK, tags=["Projects"])
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projet introuvable.",
        )

    # Clean up files on disk
    for doc in project.documents:
        if os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except OSError:
                pass

    db.delete(project)
    db.commit()
    return {"detail": "Projet supprimé avec succès."}


# ==============================================================================
# Documents Routes
# ==============================================================================

@app.post(
    "/api/projects/{project_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Documents"],
)
def upload_document(
    project_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projet introuvable.",
        )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le nom du fichier ne peut pas être vide.",
        )

    # Sanitize and create safe storage filename
    safe_basename = os.path.basename(file.filename)
    extension = os.path.splitext(safe_basename)[1].lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Type de fichier non autorisé. Formats acceptés : "
            "PDF, images, textes et documents bureautiques.",
        )

    unique_prefix = uuid.uuid4().hex[:12]
    stored_name = f"{project_id}_{unique_prefix}_{safe_basename}"
    file_path = os.path.join(UPLOAD_DIR, stored_name)

    max_bytes = settings.max_upload_bytes
    max_mo = max_bytes / (1024 * 1024)
    written = 0
    try:
        with open(file_path, "wb") as buffer:
            while True:
                chunk = file.file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    buffer.close()
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Fichier trop volumineux : la taille maximale autorisée "
                        f"est de {max_mo:.0f} Mo.",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Échec de l'enregistrement du document pour le projet %s", project_id)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Échec de l'enregistrement du fichier. Veuillez réessayer.",
        )

    document = Document(
        project_id=project.id,
        filename=safe_basename,
        file_path=file_path,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@app.get(
    "/api/projects/{project_id}/documents/{document_id}/download",
    tags=["Documents"],
)
def download_document(
    project_id: int,
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projet introuvable.",
        )

    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.project_id == project_id)
        .first()
    )
    if not doc or not os.path.exists(doc.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document introuvable sur le serveur.",
        )

    return FileResponse(
        path=doc.file_path,
        filename=doc.filename,
        media_type="application/octet-stream",
    )


@app.delete(
    "/api/projects/{project_id}/documents/{document_id}",
    status_code=status.HTTP_200_OK,
    tags=["Documents"],
)
def delete_document(
    project_id: int,
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projet introuvable.",
        )

    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.project_id == project_id)
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document introuvable.",
        )

    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass

    db.delete(doc)
    db.commit()
    return {"detail": "Document supprimé."}
