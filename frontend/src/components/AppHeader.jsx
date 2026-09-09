import React from 'react';
import { displayName } from '../utils/format';

/** En-tête : marque, état de l'API, identité et actions de compte. */
export default function AppHeader({ user, apiHealthy, onLogout, onChangePassword }) {
  const isAdmin = user?.role === 'admin';

  return (
    <header>
      <div className="brand">
        <svg
          className="brand-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect width="18" height="18" x="3" y="3" rx="2" />
          <path d="M3 9h18" />
          <path d="M9 21V9" />
        </svg>
        Portail Client
      </div>

      <div className="header-actions">
        <span
          title={apiHealthy ? 'API connectée' : 'API inaccessible'}
          style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}
        >
          <span className={`health-dot ${apiHealthy ? 'ok' : 'error'}`}></span>
          {apiHealthy ? 'Système opérationnel' : 'Hors ligne'}
        </span>

        {user && (
          <>
            <span className="user-badge">
              {displayName(user)}
              <span className={`role-chip ${isAdmin ? 'role-admin' : 'role-client'}`}>
                {isAdmin ? 'Prestataire' : 'Client'}
              </span>
            </span>
            <button className="btn btn-secondary btn-sm" onClick={onChangePassword}>
              Mot de passe
            </button>
            <button className="btn btn-secondary btn-sm" onClick={onLogout}>
              Déconnexion
            </button>
          </>
        )}
      </div>
    </header>
  );
}
