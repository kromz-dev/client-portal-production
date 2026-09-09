import React, { useState, useEffect, useCallback } from 'react';
import {
  api,
  getToken,
  clearToken,
  describeError,
  setUnauthorizedHandler,
} from './api';

import AppHeader from './components/AppHeader';
import LoginForm from './components/LoginForm';
import Dashboard from './components/Dashboard';
import ProjectList from './components/ProjectList';
import ProjectDetail from './components/ProjectDetail';
import ProjectFormModal from './components/ProjectFormModal';
import ClientsView from './components/ClientsView';
import ChangePasswordModal from './components/ChangePasswordModal';

/**
 * Coquille de l'application : authentification, navigation entre les vues et
 * notifications. Toute la logique métier vit dans les composants de
 * `components/` ; ce fichier se contente de les orchestrer.
 *
 * L'inscription libre n'existe pas : les comptes clients sont créés par le
 * prestataire depuis la vue « Clients » (POST /api/clients).
 */
export default function App() {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);
  const [apiHealthy, setApiHealthy] = useState(true);

  // Navigation : 'dashboard' | 'projects' | 'clients'
  const [view, setView] = useState('dashboard');
  const [selectedProjectId, setSelectedProjectId] = useState(null);

  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsError, setProjectsError] = useState('');

  const [createOpen, setCreateOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [notice, setNotice] = useState('');

  const isAdmin = user?.role === 'admin';

  const notify = useCallback((message) => {
    setNotice(message);
  }, []);

  // Le message de confirmation s'efface tout seul.
  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(''), 5000);
    return () => clearTimeout(timer);
  }, [notice]);

  const resetSession = useCallback(() => {
    setUser(null);
    setProjects([]);
    setSelectedProjectId(null);
    setView('dashboard');
  }, []);

  const loadProjects = useCallback(async () => {
    setProjectsLoading(true);
    setProjectsError('');
    try {
      setProjects(await api.getProjects());
    } catch (err) {
      setProjectsError(describeError(err, 'Impossible de charger les projets.'));
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  // Un 401 sur n'importe quelle requête ramène à l'écran de connexion.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      resetSession();
      setNotice('Votre session a expiré. Veuillez vous reconnecter.');
    });
    return () => setUnauthorizedHandler(null);
  }, [resetSession]);

  useEffect(() => {
    async function init() {
      try {
        await api.checkHealth();
        setApiHealthy(true);
      } catch {
        setApiHealthy(false);
      }

      if (getToken()) {
        try {
          setUser(await api.getMe());
        } catch {
          clearToken();
          setUser(null);
        }
      }
      setBooting(false);
    }
    init();
  }, []);

  // Les projets se (re)chargent dès qu'un compte est actif.
  useEffect(() => {
    if (user) {
      loadProjects();
    }
  }, [user, loadProjects]);

  function handleAuthenticated(profile) {
    setUser(profile);
    setView('dashboard');
    setSelectedProjectId(null);
  }

  function handleLogout() {
    api.logout();
    resetSession();
  }

  function openProject(projectId) {
    setSelectedProjectId(projectId);
  }

  function leaveProject() {
    setSelectedProjectId(null);
  }

  function goTo(nextView) {
    setSelectedProjectId(null);
    setView(nextView);
  }

  if (booting) {
    return (
      <div className="app-container">
        <div className="empty-state">
          <p className="muted">Chargement du portail client…</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="app-container">
        {!apiHealthy && (
          <div className="alert alert-danger" style={{ margin: '1.5rem' }}>
            Le serveur est injoignable. La connexion échouera tant qu'il ne
            répond pas.
          </div>
        )}
        <LoginForm onAuthenticated={handleAuthenticated} />
      </div>
    );
  }

  return (
    <div className="app-container">
      <AppHeader
        user={user}
        apiHealthy={apiHealthy}
        onLogout={handleLogout}
        onChangePassword={() => setPasswordOpen(true)}
      />

      {!selectedProjectId && (
        <nav className="main-nav">
          <button
            type="button"
            className={`nav-btn ${view === 'dashboard' ? 'active' : ''}`}
            onClick={() => goTo('dashboard')}
          >
            Tableau de bord
          </button>
          <button
            type="button"
            className={`nav-btn ${view === 'projects' ? 'active' : ''}`}
            onClick={() => goTo('projects')}
          >
            {isAdmin ? 'Projets' : 'Mes projets'}
          </button>
          {isAdmin && (
            <button
              type="button"
              className={`nav-btn ${view === 'clients' ? 'active' : ''}`}
              onClick={() => goTo('clients')}
            >
              Clients
            </button>
          )}
        </nav>
      )}

      <main className="main-content">
        {notice && <div className="alert alert-success">{notice}</div>}

        {selectedProjectId ? (
          <ProjectDetail
            projectId={selectedProjectId}
            user={user}
            onBack={leaveProject}
            /* Signale que la fiche a changé : on rafraîchit la liste en
               arrière-plan sans quitter le projet. La suppression, elle,
               appelle `onBack` de son côté. */
            onProjectChanged={loadProjects}
            onNotify={notify}
          />
        ) : (
          <>
            {view === 'dashboard' && (
              <Dashboard user={user} onOpenProject={openProject} />
            )}

            {view === 'projects' && (
              <ProjectList
                user={user}
                projects={projects}
                loading={projectsLoading}
                error={projectsError}
                onOpenProject={openProject}
                onCreate={() => setCreateOpen(true)}
                onReload={loadProjects}
              />
            )}

            {/* Garde-fou : la vue Clients reste inaccessible à un compte client
                même si `view` était forcé à 'clients'. */}
            {view === 'clients' &&
              (isAdmin ? (
                <ClientsView onNotify={notify} />
              ) : (
                <div className="alert alert-danger">
                  Vous n'avez pas les droits nécessaires pour cette page.
                </div>
              ))}
          </>
        )}
      </main>

      {createOpen && (
        <ProjectFormModal
          project={null}
          onClose={() => setCreateOpen(false)}
          onSaved={() => {
            setCreateOpen(false);
            loadProjects();
            notify('Le projet a été créé.');
          }}
        />
      )}

      {passwordOpen && (
        <ChangePasswordModal
          onClose={() => setPasswordOpen(false)}
          onSuccess={() => {
            setPasswordOpen(false);
            notify('Votre mot de passe a été modifié.');
          }}
        />
      )}
    </div>
  );
}
