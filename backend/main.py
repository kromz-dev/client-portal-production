import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload, selectinload

from auth import (
    create_access_token,
    get_current_admin,
    get_current_user,
    get_password_hash,
    verify_password,
)
from config import settings
from database import SessionLocal, get_db
from models import Document, Event, Message, Milestone, Project, User, utcnow
from schemas import (
    ChangePassword,
    ClientCreate,
    ClientListItem,
    ClientResponse,
    DocumentResponse,
    DocumentReview,
    EventResponse,
    MessageCreate,
    MessageResponse,
    MilestoneCreate,
    MilestoneResponse,
    MilestoneUpdate,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectUpdate,
    Token,
    UserLogin,
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

_PROJECT_STATUSES = ("En attente", "En cours", "Terminé")


# ==============================================================================
# Amorçage du compte prestataire (administrateur)
# ==============================================================================

def ensure_bootstrap_admin(db: Session) -> None:
    """Garantit l'existence d'au moins un compte `role == "admin"`.

    Stratégie (dans l'ordre) :
      1. Un administrateur existe déjà -> ne rien faire.
      2. `BOOTSTRAP_ADMIN_EMAIL` est défini : promouvoir le compte portant cet
         email s'il existe, sinon le créer si `BOOTSTRAP_ADMIN_PASSWORD` est
         également fourni.
      3. Hors production et au moins un utilisateur : promouvoir le plus ancien.
      4. Sinon : journaliser un avertissement.
    """
    existing_admin = db.query(User).filter(User.role == "admin").first()
    if existing_admin is not None:
        return

    bootstrap_email = (settings.bootstrap_admin_email or "").strip().lower()
    if bootstrap_email:
        user = db.query(User).filter(User.email == bootstrap_email).first()
        if user is not None:
            user.role = "admin"
            db.commit()
            logger.info(
                "Amorçage : le compte %s est promu administrateur (prestataire).",
                bootstrap_email,
            )
            return
        if settings.bootstrap_admin_password:
            user = User(
                email=bootstrap_email,
                hashed_password=get_password_hash(settings.bootstrap_admin_password),
                role="admin",
                full_name="Prestataire",
            )
            db.add(user)
            db.commit()
            logger.info(
                "Amorçage : compte administrateur %s créé.", bootstrap_email
            )
            return
        logger.warning(
            "BOOTSTRAP_ADMIN_EMAIL est défini (%s) mais aucun compte ne correspond "
            "et BOOTSTRAP_ADMIN_PASSWORD est absent : aucun administrateur amorcé.",
            bootstrap_email,
        )
        return

    if settings.environment != "production":
        oldest = db.query(User).order_by(User.id.asc()).first()
        if oldest is not None:
            oldest.role = "admin"
            db.commit()
            logger.warning(
                "Amorçage (hors production) : le compte le plus ancien %s est "
                "promu administrateur faute de BOOTSTRAP_ADMIN_EMAIL.",
                oldest.email,
            )
            return

    logger.warning(
        "Aucun administrateur : définissez BOOTSTRAP_ADMIN_EMAIL "
        "(et éventuellement BOOTSTRAP_ADMIN_PASSWORD) pour amorcer le compte prestataire."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        ensure_bootstrap_admin(db)
    except Exception:
        logger.exception("Échec de l'amorçage du compte administrateur.")
    finally:
        db.close()
    yield


app = FastAPI(
    title="Portail Client API",
    description="API minimale et robuste pour le portail client",
    version=settings.app_version,
    lifespan=lifespan,
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
# Helpers
# ==============================================================================

def record_event(
    db: Session,
    project_id: int,
    actor: Optional[User],
    type_: str,
    summary: str,
) -> Event:
    """Insère un événement d'historique pour un projet.

    L'appelant reste responsable du `commit` (l'événement est ajouté à la
    session courante et flushé avec le reste de la transaction).
    """
    event = Event(
        project_id=project_id,
        actor_id=actor.id if actor is not None else None,
        type=type_,
        summary=summary,
    )
    db.add(event)
    return event


def _actor_payload(user: Optional[User]) -> Optional[dict]:
    if user is None:
        return None
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    }


def _client_payload(user: Optional[User]) -> Optional[dict]:
    if user is None:
        return None
    return {"id": user.id, "email": user.email, "full_name": user.full_name}


def _document_payload(doc: Document) -> dict:
    return {
        "id": doc.id,
        "project_id": doc.project_id,
        "filename": doc.filename,
        "uploaded_at": doc.uploaded_at,
        "uploaded_by": doc.uploaded_by,
        "kind": doc.kind,
        "review_status": doc.review_status,
        "review_comment": doc.review_comment,
        "reviewed_at": doc.reviewed_at,
    }


def _milestone_payload(m: Milestone) -> dict:
    return {
        "id": m.id,
        "project_id": m.project_id,
        "title": m.title,
        "position": m.position,
        "status": m.status,
        "due_date": m.due_date,
    }


def _event_payload(event: Event) -> dict:
    return {
        "id": event.id,
        "type": event.type,
        "summary": event.summary,
        "created_at": event.created_at,
        "actor": _actor_payload(event.actor),
    }


def _message_payload(message: Message) -> dict:
    return {
        "id": message.id,
        "body": message.body,
        "created_at": message.created_at,
        "author": _actor_payload(message.author),
    }


def _project_payload(
    project: Project,
    db: Session,
    *,
    detail: bool = False,
    message_count: Optional[int] = None,
) -> dict:
    milestones = sorted(project.milestones, key=lambda m: (m.position, m.id))
    milestones_done = sum(1 for m in project.milestones if m.status == "fait")
    if message_count is None:
        message_count = (
            db.query(func.count(Message.id))
            .filter(Message.project_id == project.id)
            .scalar()
            or 0
        )

    payload = {
        "id": project.id,
        "user_id": project.user_id,
        "client_id": project.client_id,
        "title": project.title,
        "description": project.description,
        "status": project.status,
        "created_at": project.created_at,
        "due_date": project.due_date,
        "started_at": project.started_at,
        "client": _client_payload(project.client),
        "documents": [
            _document_payload(d)
            for d in sorted(project.documents, key=lambda d: d.id)
        ],
        "message_count": message_count,
        "milestones_done": milestones_done,
        "milestones_total": len(project.milestones),
    }

    if detail:
        payload["milestones"] = [_milestone_payload(m) for m in milestones]
        recent_events = (
            db.query(Event)
            .options(joinedload(Event.actor))
            .filter(Event.project_id == project.id)
            .order_by(Event.created_at.desc(), Event.id.desc())
            .limit(50)
            .all()
        )
        payload["events"] = [_event_payload(e) for e in recent_events]

    return payload


def _load_project_for_access(db: Session, project_id: int, user: User) -> Project:
    """Renvoie le projet si l'utilisateur y a accès, sinon lève une 404.

    Un prestataire (`admin`) accède à tous les projets ; un client uniquement
    aux projets dont il est le destinataire. Dans les deux cas d'échec on
    renvoie 404 pour ne pas divulguer l'existence du projet.
    """
    project = (
        db.query(Project)
        .options(
            selectinload(Project.documents),
            selectinload(Project.milestones),
            joinedload(Project.client),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Projet introuvable."
        )
    if user.role != "admin" and project.client_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Projet introuvable."
        )
    return project


def _get_client_or_400(db: Session, client_id: int) -> User:
    client = db.query(User).filter(User.id == client_id).first()
    if client is None or client.role != "client":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le client indiqué est introuvable.",
        )
    return client


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


@app.post("/api/auth/change-password", tags=["Auth"])
@limiter.limit("10/minute")
def change_password(
    request: Request,
    body: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mot de passe actuel incorrect.",
        )
    current_user.hashed_password = get_password_hash(body.new_password)
    db.commit()
    return {"detail": "Mot de passe mis à jour."}


# ==============================================================================
# Clients Routes (gestion par le prestataire)
# ==============================================================================

@app.get("/api/clients", response_model=List[ClientListItem], tags=["Clients"])
def list_clients(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    counts = dict(
        db.query(Project.client_id, func.count(Project.id))
        .group_by(Project.client_id)
        .all()
    )
    clients = (
        db.query(User)
        .filter(User.role == "client")
        .order_by(User.created_at.asc(), User.id.asc())
        .all()
    )
    return [
        {
            "id": c.id,
            "email": c.email,
            "full_name": c.full_name,
            "created_at": c.created_at,
            "project_count": counts.get(c.id, 0),
        }
        for c in clients
    ]


@app.post(
    "/api/clients",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Clients"],
)
def create_client(
    client_in: ClientCreate,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    normalized_email = client_in.email.strip().lower()
    if db.query(User).filter(User.email == normalized_email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un compte avec cet email existe déjà.",
        )
    client = User(
        email=normalized_email,
        full_name=client_in.full_name.strip(),
        hashed_password=get_password_hash(client_in.password),
        role="client",
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


# ==============================================================================
# Projects Routes
# ==============================================================================

@app.get("/api/projects", response_model=List[ProjectResponse], tags=["Projects"])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Project).options(
        selectinload(Project.documents),
        selectinload(Project.milestones),
        joinedload(Project.client),
    )
    if current_user.role != "admin":
        query = query.filter(Project.client_id == current_user.id)
    projects = query.order_by(Project.created_at.desc(), Project.id.desc()).all()

    message_counts = dict(
        db.query(Message.project_id, func.count(Message.id))
        .group_by(Message.project_id)
        .all()
    )
    return [
        _project_payload(p, db, message_count=message_counts.get(p.id, 0))
        for p in projects
    ]


@app.post(
    "/api/projects",
    response_model=ProjectDetailResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Projects"],
)
def create_project(
    project_in: ProjectCreate,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _get_client_or_400(db, project_in.client_id)
    project = Project(
        user_id=current_admin.id,
        client_id=project_in.client_id,
        title=project_in.title.strip(),
        description=project_in.description.strip() if project_in.description else None,
        status=project_in.status or "En cours",
        due_date=project_in.due_date,
        started_at=project_in.started_at,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_payload(project, db, detail=True, message_count=0)


@app.get(
    "/api/projects/{project_id}",
    response_model=ProjectDetailResponse,
    tags=["Projects"],
)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _load_project_for_access(db, project_id, current_user)
    return _project_payload(project, db, detail=True)


@app.put(
    "/api/projects/{project_id}",
    response_model=ProjectDetailResponse,
    tags=["Projects"],
)
def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .options(
            selectinload(Project.documents),
            selectinload(Project.milestones),
            joinedload(Project.client),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Projet introuvable."
        )

    if project_in.client_id is not None:
        _get_client_or_400(db, project_in.client_id)
        project.client_id = project_in.client_id

    if project_in.title is not None:
        project.title = project_in.title.strip()
    if project_in.description is not None:
        project.description = (
            project_in.description.strip() if project_in.description else None
        )

    old_status = project.status
    if project_in.status is not None and project_in.status != old_status:
        project.status = project_in.status
        record_event(
            db,
            project.id,
            current_admin,
            "statut",
            f"Statut du projet : « {old_status} » → « {project_in.status} »",
        )

    if project_in.due_date is not None:
        project.due_date = project_in.due_date
    if project_in.started_at is not None:
        project.started_at = project_in.started_at

    db.commit()
    db.refresh(project)
    return _project_payload(project, db, detail=True)


@app.delete(
    "/api/projects/{project_id}",
    status_code=status.HTTP_200_OK,
    tags=["Projects"],
)
def delete_project(
    project_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .options(selectinload(Project.documents))
        .filter(Project.id == project_id)
        .first()
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Projet introuvable."
        )

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
    project = _load_project_for_access(db, project_id, current_user)
    kind = "livrable" if current_user.role == "admin" else "piece_client"

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le nom du fichier ne peut pas être vide.",
        )

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
        uploaded_by=current_user.id,
        kind=kind,
    )
    db.add(document)
    label = "Livrable déposé" if kind == "livrable" else "Pièce client déposée"
    record_event(db, project.id, current_user, "document", f"{label} : {safe_basename}")
    db.commit()
    db.refresh(document)
    return _document_payload(document)


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
    project = _load_project_for_access(db, project_id, current_user)
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.project_id == project.id)
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
    project = _load_project_for_access(db, project_id, current_user)
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.project_id == project.id)
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable."
        )

    if current_user.role != "admin":
        if doc.uploaded_by != current_user.id or doc.kind != "piece_client":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez supprimer que vos propres pièces.",
            )

    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass

    db.delete(doc)
    db.commit()
    return {"detail": "Document supprimé."}


@app.post(
    "/api/projects/{project_id}/documents/{document_id}/review",
    response_model=DocumentResponse,
    tags=["Documents"],
)
def review_document(
    project_id: int,
    document_id: int,
    review: DocumentReview,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La revue d'un livrable est réservée au client.",
        )
    project = _load_project_for_access(db, project_id, current_user)
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.project_id == project.id)
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable."
        )
    if doc.kind != "livrable":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seuls les livrables du prestataire peuvent être revus.",
        )

    doc.review_status = review.decision
    doc.review_comment = review.comment.strip() if review.comment else None
    doc.reviewed_at = utcnow()
    label = "approuvé" if review.decision == "approuve" else "révision demandée"
    record_event(
        db, project.id, current_user, "revue", f"Livrable « {doc.filename} » : {label}"
    )
    db.commit()
    db.refresh(doc)
    return _document_payload(doc)


# ==============================================================================
# Messages Routes
# ==============================================================================

@app.get(
    "/api/projects/{project_id}/messages",
    response_model=List[MessageResponse],
    tags=["Messages"],
)
def list_messages(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _load_project_for_access(db, project_id, current_user)
    messages = (
        db.query(Message)
        .options(joinedload(Message.author))
        .filter(Message.project_id == project.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    return [_message_payload(m) for m in messages]


@app.post(
    "/api/projects/{project_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Messages"],
)
def create_message(
    project_id: int,
    message_in: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _load_project_for_access(db, project_id, current_user)
    body = message_in.body.strip()
    if not body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le message ne peut pas être vide.",
        )
    message = Message(project_id=project.id, author_id=current_user.id, body=body)
    db.add(message)
    author_name = current_user.full_name or current_user.email
    record_event(
        db, project.id, current_user, "message", f"Nouveau message de {author_name}"
    )
    db.commit()
    db.refresh(message)
    return _message_payload(message)


# ==============================================================================
# Events Routes
# ==============================================================================

@app.get(
    "/api/projects/{project_id}/events",
    response_model=List[EventResponse],
    tags=["Events"],
)
def list_events(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _load_project_for_access(db, project_id, current_user)
    events = (
        db.query(Event)
        .options(joinedload(Event.actor))
        .filter(Event.project_id == project.id)
        .order_by(Event.created_at.desc(), Event.id.desc())
        .limit(50)
        .all()
    )
    return [_event_payload(e) for e in events]


# ==============================================================================
# Milestones Routes
# ==============================================================================

@app.post(
    "/api/projects/{project_id}/milestones",
    response_model=MilestoneResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Milestones"],
)
def create_milestone(
    project_id: int,
    milestone_in: MilestoneCreate,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Projet introuvable."
        )
    if milestone_in.position is not None:
        position = milestone_in.position
    else:
        position = (
            db.query(func.coalesce(func.max(Milestone.position), -1))
            .filter(Milestone.project_id == project_id)
            .scalar()
        ) + 1
    milestone = Milestone(
        project_id=project_id,
        title=milestone_in.title.strip(),
        due_date=milestone_in.due_date,
        position=position,
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return _milestone_payload(milestone)


@app.put(
    "/api/projects/{project_id}/milestones/{milestone_id}",
    response_model=MilestoneResponse,
    tags=["Milestones"],
)
def update_milestone(
    project_id: int,
    milestone_id: int,
    milestone_in: MilestoneUpdate,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    milestone = (
        db.query(Milestone)
        .filter(Milestone.id == milestone_id, Milestone.project_id == project_id)
        .first()
    )
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Jalon introuvable."
        )

    if milestone_in.title is not None:
        milestone.title = milestone_in.title.strip()
    if milestone_in.due_date is not None:
        milestone.due_date = milestone_in.due_date
    if milestone_in.position is not None:
        milestone.position = milestone_in.position

    if milestone_in.status is not None and milestone_in.status != milestone.status:
        became_done = milestone_in.status == "fait"
        milestone.status = milestone_in.status
        if became_done:
            record_event(
                db,
                project_id,
                current_admin,
                "jalon",
                f"Jalon terminé : « {milestone.title} »",
            )

    db.commit()
    db.refresh(milestone)
    return _milestone_payload(milestone)


@app.delete(
    "/api/projects/{project_id}/milestones/{milestone_id}",
    status_code=status.HTTP_200_OK,
    tags=["Milestones"],
)
def delete_milestone(
    project_id: int,
    milestone_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    milestone = (
        db.query(Milestone)
        .filter(Milestone.id == milestone_id, Milestone.project_id == project_id)
        .first()
    )
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Jalon introuvable."
        )
    db.delete(milestone)
    db.commit()
    return {"detail": "Jalon supprimé."}


# ==============================================================================
# Dashboard
# ==============================================================================

def _recent_events_with_project(db: Session, *, client_id: Optional[int], limit: int = 15):
    query = (
        db.query(Event, Project.title)
        .join(Project, Event.project_id == Project.id)
        .options(joinedload(Event.actor))
    )
    if client_id is not None:
        query = query.filter(Project.client_id == client_id)
    rows = query.order_by(Event.created_at.desc(), Event.id.desc()).limit(limit).all()
    result = []
    for event, project_title in rows:
        item = _event_payload(event)
        item["project_id"] = event.project_id
        item["project_title"] = project_title
        result.append(item)
    return result


def _projects_by_status(db: Session, *, client_id: Optional[int]) -> dict:
    query = db.query(Project.status, func.count(Project.id))
    if client_id is not None:
        query = query.filter(Project.client_id == client_id)
    raw = dict(query.group_by(Project.status).all())
    return {label: raw.get(label, 0) for label in _PROJECT_STATUSES}


@app.get("/api/dashboard", tags=["Dashboard"])
def dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == "admin":
        clients_count = (
            db.query(func.count(User.id)).filter(User.role == "client").scalar() or 0
        )
        projects_total = db.query(func.count(Project.id)).scalar() or 0
        documents_pending_review = (
            db.query(func.count(Document.id))
            .filter(Document.kind == "livrable", Document.review_status.is_(None))
            .scalar()
            or 0
        )
        return {
            "clients_count": clients_count,
            "projects_total": projects_total,
            "projects_by_status": _projects_by_status(db, client_id=None),
            "documents_pending_review": documents_pending_review,
            "recent_events": _recent_events_with_project(db, client_id=None),
        }

    projects_total = (
        db.query(func.count(Project.id))
        .filter(Project.client_id == current_user.id)
        .scalar()
        or 0
    )
    deliverables_to_review = (
        db.query(func.count(Document.id))
        .join(Project, Document.project_id == Project.id)
        .filter(
            Project.client_id == current_user.id,
            Document.kind == "livrable",
            Document.review_status.is_(None),
        )
        .scalar()
        or 0
    )
    return {
        "projects_total": projects_total,
        "projects_by_status": _projects_by_status(db, client_id=current_user.id),
        "deliverables_to_review": deliverables_to_review,
        "recent_events": _recent_events_with_project(db, client_id=current_user.id),
    }
