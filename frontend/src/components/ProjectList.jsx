import React from 'react';
import { displayName, formatDate, plural, statusBadgeClass } from '../utils/format';

function ProgressBar({ done, total }) {
  const percent = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="progress" title={`${done} jalon(s) terminé(s) sur ${total}`}>
      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${percent}%` }} />
      </div>
      <span className="progress-label">
        {done}/{total} jalons
      </span>
    </div>
  );
}

/** Liste des projets. Le prestataire voit tous les projets, le client les siens. */
export default function ProjectList({ user, projects, loading, error, onOpenProject, onCreate, onReload }) {
  const isAdmin = user.role === 'admin';

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">{isAdmin ? 'Projets' : 'Mes projets'}</h1>
          <p className="page-subtitle">
            {isAdmin
              ? 'Pilotez les projets de vos clients : jalons, livrables et échanges.'
              : 'Suivez l’avancement de vos dossiers et récupérez vos livrables.'}
          </p>
        </div>
        {isAdmin && (
          <button className="btn btn-primary" onClick={onCreate}>
            + Nouveau projet
          </button>
        )}
      </div>

      {error && (
        <div className="alert alert-danger">
          {error}{' '}
          <button type="button" className="link-button" onClick={onReload}>
            Réessayer
          </button>
        </div>
      )}

      {loading ? (
        <div className="empty-state">Chargement des projets...</div>
      ) : projects.length > 0 ? (
        <div className="project-grid">
          {projects.map((project) => (
            <div
              key={project.id}
              className="project-card"
              role="button"
              tabIndex={0}
              onClick={() => onOpenProject(project.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onOpenProject(project.id);
                }
              }}
            >
              <div>
                <div className="project-card-header">
                  <h3 className="project-title">{project.title}</h3>
                  <span className={`badge ${statusBadgeClass(project.status)}`}>
                    {project.status}
                  </span>
                </div>

                {isAdmin && (
                  <p className="project-client">
                    Client :{' '}
                    {project.client ? displayName(project.client) : 'aucun client rattaché'}
                  </p>
                )}

                <p className="project-desc">{project.description || 'Pas de description.'}</p>

                {project.milestones_total > 0 && (
                  <ProgressBar
                    done={project.milestones_done || 0}
                    total={project.milestones_total}
                  />
                )}
              </div>

              <div className="project-meta">
                <span>
                  {plural(project.documents?.length || 0, 'document')} ·{' '}
                  {plural(project.message_count || 0, 'message')}
                </span>
                <span>
                  {project.due_date
                    ? `Échéance : ${formatDate(project.due_date)}`
                    : formatDate(project.created_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          {isAdmin ? (
            <>
              <p style={{ marginBottom: '1rem' }}>Aucun projet pour le moment.</p>
              <button className="btn btn-primary btn-sm" onClick={onCreate}>
                Créer le premier projet
              </button>
            </>
          ) : (
            <p>
              Aucun projet ne vous est encore rattaché. Votre prestataire vous préviendra dès
              qu’un dossier sera ouvert.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
