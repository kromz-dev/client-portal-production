import React, { useCallback, useEffect, useState } from 'react';
import { api, describeError } from '../api';
import { displayName, eventTypeLabel, formatDateTime, PROJECT_STATUSES } from '../utils/format';

function StatCard({ label, value, hint }) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

/**
 * Tableau de bord. Le backend renvoie un contenu différent selon le rôle :
 * - prestataire : clients_count, projects_total, projects_by_status,
 *   documents_pending_review, recent_events ;
 * - client : projects_total, projects_by_status, deliverables_to_review,
 *   recent_events.
 */
export default function Dashboard({ user, onOpenProject }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const isAdmin = user.role === 'admin';

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await api.getDashboard());
    } catch (err) {
      setError(describeError(err, 'Impossible de charger le tableau de bord.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <div className="empty-state">Chargement du tableau de bord...</div>;
  }

  if (error) {
    return (
      <div>
        <div className="alert alert-danger">{error}</div>
        <button className="btn btn-secondary btn-sm" onClick={load}>
          Réessayer
        </button>
      </div>
    );
  }

  if (!data) return null;

  const byStatus = data.projects_by_status || {};
  const events = data.recent_events || [];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Tableau de bord</h1>
          <p className="page-subtitle">
            {isAdmin
              ? "Vue d'ensemble de votre activité et des dernières actions de vos clients."
              : 'Vue d’ensemble de vos projets et des dernières actions de votre prestataire.'}
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={load}>
          Actualiser
        </button>
      </div>

      <div className="stat-grid">
        {isAdmin && <StatCard label="Clients" value={data.clients_count ?? 0} />}
        <StatCard label="Projets" value={data.projects_total ?? 0} />
        {isAdmin ? (
          <StatCard
            label="Livrables sans revue"
            value={data.documents_pending_review ?? 0}
            hint="En attente d’un retour client"
          />
        ) : (
          <StatCard
            label="Livrables à examiner"
            value={data.deliverables_to_review ?? 0}
            hint="En attente de votre validation"
          />
        )}
      </div>

      <h2 className="section-title">Répartition des projets</h2>
      <div className="status-breakdown">
        {PROJECT_STATUSES.map((status) => (
          <div key={status} className="status-breakdown-item">
            <span className="status-breakdown-count">{byStatus[status] ?? 0}</span>
            <span className="status-breakdown-label">{status}</span>
          </div>
        ))}
      </div>

      <h2 className="section-title">Activité récente</h2>
      {events.length > 0 ? (
        <ul className="timeline">
          {events.map((event) => (
            <li key={event.id} className="timeline-item">
              <span className="timeline-type">{eventTypeLabel(event.type)}</span>
              <div className="timeline-body">
                <p className="timeline-summary">{event.summary}</p>
                <p className="timeline-meta">
                  {event.project_title && (
                    <>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => onOpenProject(event.project_id)}
                      >
                        {event.project_title}
                      </button>
                      {' · '}
                    </>
                  )}
                  {displayName(event.actor)} · {formatDateTime(event.created_at)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty-state">Aucune activité pour le moment.</div>
      )}
    </div>
  );
}
