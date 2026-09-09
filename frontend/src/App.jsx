import React, { useState, useEffect, useRef } from 'react';
import { api, getToken, clearToken } from './api';

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiHealthy, setApiHealthy] = useState(true);
  const [authMode, setAuthMode] = useState('login'); // 'login' | 'register'
  const [authError, setAuthError] = useState('');
  const [authSuccess, setAuthSuccess] = useState('');

  // Form states for login/register
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');

  // Projects state
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [currentProject, setCurrentProject] = useState(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newStatus, setNewStatus] = useState('En cours');

  // File upload state
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  // Initialize app
  useEffect(() => {
    async function init() {
      try {
        await api.checkHealth();
        setApiHealthy(true);
      } catch {
        setApiHealthy(false);
      }

      const token = getToken();
      if (token) {
        try {
          const profile = await api.getMe();
          setUser(profile);
          loadProjects();
        } catch {
          clearToken();
          setUser(null);
        }
      }
      setLoading(false);
    }
    init();
  }, []);

  async function loadProjects() {
    try {
      const data = await api.getProjects();
      setProjects(data);
    } catch (err) {
      console.error('Failed to load projects:', err);
    }
  }

  async function loadProjectDetails(id) {
    try {
      const data = await api.getProject(id);
      setCurrentProject(data);
      setSelectedProjectId(id);
    } catch (err) {
      alert(err.message || 'Impossible de charger le projet');
    }
  }

  // Handle Authentication
  async function handleAuthSubmit(e) {
    e.preventDefault();
    setAuthError('');
    setAuthSuccess('');

    try {
      if (authMode === 'login') {
        await api.login(authEmail, authPassword);
        const me = await api.getMe();
        setUser(me);
        loadProjects();
      } else {
        await api.register(authEmail, authPassword);
        setAuthSuccess('Compte créé avec succès ! Connexion automatique...');
        await api.login(authEmail, authPassword);
        const me = await api.getMe();
        setUser(me);
        loadProjects();
      }
      setAuthEmail('');
      setAuthPassword('');
    } catch (err) {
      setAuthError(err.message || 'Une erreur est survenue');
    }
  }

  function handleLogout() {
    api.logout();
    setUser(null);
    setSelectedProjectId(null);
    setCurrentProject(null);
    setProjects([]);
  }

  // Handle Projects
  async function handleCreateProject(e) {
    e.preventDefault();
    if (!newTitle.trim()) return;

    try {
      await api.createProject({
        title: newTitle.trim(),
        description: newDesc.trim() || null,
        status: newStatus,
      });
      setNewTitle('');
      setNewDesc('');
      setNewStatus('En cours');
      setIsCreateModalOpen(false);
      loadProjects();
    } catch (err) {
      alert(err.message || 'Erreur lors de la création');
    }
  }

  async function handleUpdateStatus(newVal) {
    if (!currentProject) return;
    try {
      const updated = await api.updateProject(currentProject.id, { status: newVal });
      setCurrentProject(updated);
      loadProjects();
    } catch (err) {
      alert(err.message || 'Erreur lors de la mise à jour');
    }
  }

  async function handleDeleteProject() {
    if (!currentProject) return;
    if (!window.confirm(`Êtes-vous sûr de vouloir supprimer le projet "${currentProject.title}" ?`)) {
      return;
    }
    try {
      await api.deleteProject(currentProject.id);
      setSelectedProjectId(null);
      setCurrentProject(null);
      loadProjects();
    } catch (err) {
      alert(err.message || 'Erreur lors de la suppression');
    }
  }

  // Handle Documents
  async function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file || !currentProject) return;

    setUploading(true);
    try {
      await api.uploadDocument(currentProject.id, file);
      await loadProjectDetails(currentProject.id);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      alert(err.message || "Erreur lors de l'envoi du document");
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteDocument(docId) {
    if (!window.confirm('Supprimer ce document ?')) return;
    try {
      await api.deleteDocument(currentProject.id, docId);
      await loadProjectDetails(currentProject.id);
    } catch (err) {
      alert(err.message || 'Erreur lors de la suppression');
    }
  }

  if (loading) {
    return (
      <div className="app-container" style={{ display: 'grid', placeItems: 'center', minHeight: '100vh' }}>
        <p style={{ color: 'var(--text-muted)' }}>Chargement du portail client...</p>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Header */}
      <header>
        <div className="brand">
          <svg className="brand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2" />
            <path d="M3 9h18" />
            <path d="M9 21V9" />
          </svg>
          Portail Client
        </div>
        <div className="header-actions">
          <span title={apiHealthy ? 'API connectée' : 'API inaccessible'} style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            <span className={`health-dot ${apiHealthy ? 'ok' : 'error'}`}></span>
            {apiHealthy ? 'Système opérationnel' : 'Hors ligne'}
          </span>

          {user && (
            <>
              <span className="user-badge">{user.email}</span>
              <button className="btn btn-secondary btn-sm" onClick={handleLogout}>
                Déconnexion
              </button>
            </>
          )}
        </div>
      </header>

      <main>
        {/* Unauthenticated View */}
        {!user ? (
          <div className="auth-box">
            <div className="auth-tabs">
              <button
                className={`auth-tab-btn ${authMode === 'login' ? 'active' : ''}`}
                onClick={() => { setAuthMode('login'); setAuthError(''); setAuthSuccess(''); }}
              >
                Connexion
              </button>
              <button
                className={`auth-tab-btn ${authMode === 'register' ? 'active' : ''}`}
                onClick={() => { setAuthMode('register'); setAuthError(''); setAuthSuccess(''); }}
              >
                Créer un compte
              </button>
            </div>

            {authError && <div className="alert alert-danger">{authError}</div>}
            {authSuccess && <div className="alert alert-success">{authSuccess}</div>}

            <form onSubmit={handleAuthSubmit}>
              <div className="form-group">
                <label htmlFor="email">Adresse email</label>
                <input
                  id="email"
                  type="email"
                  required
                  placeholder="nom@exemple.com"
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="password">Mot de passe</label>
                <input
                  id="password"
                  type="password"
                  required
                  placeholder="••••••••"
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                />
              </div>

              <button type="submit" className="btn btn-primary btn-block" style={{ marginTop: '1rem' }}>
                {authMode === 'login' ? 'Se connecter' : 'Créer mon compte'}
              </button>
            </form>
          </div>
        ) : selectedProjectId && currentProject ? (
          /* Project Detail View */
          <div className="detail-view">
            <button className="breadcrumb" onClick={() => { setSelectedProjectId(null); setCurrentProject(null); }}>
              ← Retour à mes projets
            </button>

            <div className="detail-header">
              <div>
                <h1 className="page-title" style={{ marginBottom: '0.5rem' }}>{currentProject.title}</h1>
                <p style={{ color: 'var(--text-secondary)', maxWidth: '600px' }}>
                  {currentProject.description || 'Aucune description renseignée.'}
                </p>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                  Créé le {new Date(currentProject.created_at).toLocaleDateString('fr-FR')}
                </p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.75rem' }}>
                <div className="status-picker">
                  <label htmlFor="status-select">Statut :</label>
                  <select
                    id="status-select"
                    value={currentProject.status}
                    onChange={(e) => handleUpdateStatus(e.target.value)}
                  >
                    <option value="En attente">En attente</option>
                    <option value="En cours">En cours</option>
                    <option value="Terminé">Terminé</option>
                  </select>
                </div>
                <button className="btn btn-danger btn-sm" onClick={handleDeleteProject}>
                  Supprimer le projet
                </button>
              </div>
            </div>

            {/* Documents Section */}
            <h2 className="section-title">Documents du projet ({currentProject.documents?.length || 0})</h2>

            <div className="upload-zone">
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                onChange={handleFileUpload}
              />
              <p style={{ marginBottom: '0.75rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                Ajoutez un document, livrable ou devis associé à ce projet
              </p>
              <button
                className="btn btn-secondary btn-sm"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
              >
                {uploading ? 'Envoi en cours...' : 'Choisir un fichier'}
              </button>
            </div>

            {currentProject.documents && currentProject.documents.length > 0 ? (
              <ul className="doc-list">
                {currentProject.documents.map((doc) => (
                  <li key={doc.id} className="doc-item">
                    <div className="doc-info">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--primary)' }}>
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                      <div>
                        <div className="doc-name">{doc.filename}</div>
                        <div className="doc-date">Ajouté le {new Date(doc.uploaded_at).toLocaleDateString('fr-FR')}</div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() =>
                          api
                            .downloadDocument(currentProject.id, doc.id, doc.filename)
                            .catch((err) => alert(err.message || 'Erreur lors du téléchargement'))
                        }
                      >
                        Télécharger
                      </button>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => handleDeleteDocument(doc.id)}
                      >
                        Supprimer
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="empty-state">
                Aucun document n'a encore été déposé pour ce projet.
              </div>
            )}
          </div>
        ) : (
          /* Projects List View */
          <div>
            <div className="page-header">
              <div>
                <h1 className="page-title">Mes Projets</h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                  Suivez vos dossiers et téléchargez vos livrables
                </p>
              </div>
              <button className="btn btn-primary" onClick={() => setIsCreateModalOpen(true)}>
                + Nouveau projet
              </button>
            </div>

            {projects.length > 0 ? (
              <div className="project-grid">
                {projects.map((proj) => {
                  let badgeClass = 'badge-en-cours';
                  if (proj.status === 'Terminé') badgeClass = 'badge-termine';
                  if (proj.status === 'En attente') badgeClass = 'badge-en-attente';

                  return (
                    <div
                      key={proj.id}
                      className="project-card"
                      onClick={() => loadProjectDetails(proj.id)}
                    >
                      <div>
                        <div className="project-card-header">
                          <h3 className="project-title">{proj.title}</h3>
                          <span className={`badge ${badgeClass}`}>{proj.status}</span>
                        </div>
                        <p className="project-desc">
                          {proj.description || 'Pas de description.'}
                        </p>
                      </div>

                      <div className="project-meta">
                        <span>{proj.documents?.length || 0} document(s)</span>
                        <span>{new Date(proj.created_at).toLocaleDateString('fr-FR')}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state">
                <p style={{ marginBottom: '1rem' }}>Vous n'avez aucun projet pour le moment.</p>
                <button className="btn btn-primary btn-sm" onClick={() => setIsCreateModalOpen(true)}>
                  Créer votre premier projet
                </button>
              </div>
            )}
          </div>
        )}

        {/* Modal Create Project */}
        {isCreateModalOpen && (
          <div className="modal-overlay" onClick={() => setIsCreateModalOpen(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <h2 style={{ fontSize: '1.25rem', marginBottom: '1rem' }}>Nouveau Projet</h2>
              <form onSubmit={handleCreateProject}>
                <div className="form-group">
                  <label htmlFor="p-title">Titre du projet</label>
                  <input
                    id="p-title"
                    type="text"
                    required
                    placeholder="ex: Refonte site web, Audit SEO..."
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="p-desc">Description</label>
                  <textarea
                    id="p-desc"
                    rows="3"
                    placeholder="Objectifs, détails, livrables attendus..."
                    value={newDesc}
                    onChange={(e) => setNewDesc(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="p-status">Statut initial</label>
                  <select
                    id="p-status"
                    value={newStatus}
                    onChange={(e) => setNewStatus(e.target.value)}
                  >
                    <option value="En attente">En attente</option>
                    <option value="En cours">En cours</option>
                    <option value="Terminé">Terminé</option>
                  </select>
                </div>

                <div className="modal-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setIsCreateModalOpen(false)}
                  >
                    Annuler
                  </button>
                  <button type="submit" className="btn btn-primary">
                    Créer le projet
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
