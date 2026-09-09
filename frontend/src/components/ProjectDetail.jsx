import React, { useCallback, useEffect, useState } from 'react';
import DocumentSection from './DocumentSection';
import EventFeed from './EventFeed';
import MessageThread from './MessageThread';
import MilestoneSection from './MilestoneSection';
import ProjectFormModal from './ProjectFormModal';
import { api, describeError } from '../api';
import { displayName, formatDate, PROJECT_STATUSES, statusBadgeClass } from '../utils/format';

/** Fiche projet : jalons, documents, messages et journal d'activité. */
export default function ProjectDetail({ projectId, user, onBack, onProjectChanged, onNotify }) {
  const isAdmin = user.role === 'admin';

  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      setProject(await api.getProject(projectId));
    } catch (err) {
      setLoadError(describeError(err, 'Impossible de charger ce projet.'));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  // Rechargement après une action (jalon, document, message) : la fiche et la
  // liste des projets doivent refléter le nouvel état.
  const refresh = useCallback(async () => {
    try {
      setProject(await api.getProject(projectId));
    } catch (err) {
      setActionError(describeError(err, 'Impossible d’actualiser ce projet.'));
    }
    if (onProjectChanged) onProjectChanged();
  }, [projectId, onProjectChanged]);

  async function handleStatusChange(status) {
    setActionError('');
    setBusy(true);
    try {
      const updated = await api.updateProject(project.id, { status });
      setProject(updated);
      if (onProjectChanged) onProjectChanged();
    } catch (err) {
      setActionError(describeError(err, 'Impossible de changer le statut du projet.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Supprimer définitivement le projet « ${project.title} » ?`)) return;
    setActionError('');
    setBusy(true);
    try {
      await api.deleteProject(project.id);
      onNotify('Le projet a été supprimé.');
      if (onProjectChanged) onProjectChanged();
      onBack();
    } catch (err) {
      setActionError(describeError(err, 'Impossible de supprimer ce projet.'));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="empty-state">Chargement du projet...</div>;
  }

  if (loadError || !project) {
    return (
      <div className="detail-view">
        <button className="breadcrumb" onClick={onBack}>
          ← Retour aux projets
        </button>
        <div className="alert alert-danger">{loadError || 'Projet introuvable.'}</div>
      </div>
    );
  }

  return (
    <div className="detail-view">
      <button className="breadcrumb" onClick={onBack}>
        ← Retour aux projets
      </button>

      {actionError && <div className="alert alert-danger">{actionError}</div>}

      <div className="detail-header">
        <div>
          <h1 className="page-title" style={{ marginBottom: '0.5rem' }}>
            {project.title}
          </h1>
          <p style={{ color: 'var(--text-secondary)', maxWidth: '600px' }}>
            {project.description || 'Aucune description renseignée.'}
          </p>

          <dl className="detail-facts">
            {isAdmin && (
              <div>
                <dt>Client</dt>
                <dd>{project.client ? displayName(project.client) : 'Aucun client rattaché'}</dd>
              </div>
            )}
            <div>
              <dt>Créé le</dt>
              <dd>{formatDate(project.created_at)}</dd>
            </div>
            <div>
              <dt>Démarrage</dt>
              <dd>{project.started_at ? formatDate(project.started_at) : 'Non défini'}</dd>
            </div>
            <div>
              <dt>Échéance</dt>
              <dd>{project.due_date ? formatDate(project.due_date) : 'Non définie'}</dd>
            </div>
          </dl>
        </div>

        <div className="detail-header-actions">
          {isAdmin ? (
            <>
              <div className="status-picker">
                <label htmlFor="status-select">Statut :</label>
                <select
                  id="status-select"
                  value={project.status}
                  disabled={busy}
                  onChange={(event) => handleStatusChange(event.target.value)}
                >
                  {PROJECT_STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
              </div>
              <div className="detail-buttons">
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={busy}
                  onClick={() => setEditing(true)}
                >
                  Modifier
                </button>
                <button className="btn btn-danger btn-sm" disabled={busy} onClick={handleDelete}>
                  Supprimer
                </button>
              </div>
            </>
          ) : (
            <span className={`badge ${statusBadgeClass(project.status)}`}>{project.status}</span>
          )}
        </div>
      </div>

      <MilestoneSection project={project} isAdmin={isAdmin} onChanged={refresh} />

      <DocumentSection project={project} user={user} onChanged={refresh} />

      <MessageThread projectId={project.id} user={user} onPosted={refresh} />

      <EventFeed events={project.events} />

      {editing && (
        <ProjectFormModal
          project={project}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setProject(saved);
            onNotify('Le projet a été mis à jour.');
            if (onProjectChanged) onProjectChanged();
          }}
        />
      )}
    </div>
  );
}
