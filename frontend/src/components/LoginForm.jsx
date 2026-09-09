import React, { useState } from 'react';
import { api, describeError } from '../api';

/**
 * Écran de connexion. L'auto-inscription n'existe plus : les comptes clients
 * sont créés par le prestataire depuis l'espace « Clients ».
 */
export default function LoginForm({ onAuthenticated }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await api.login(email.trim(), password);
      const profile = await api.getMe();
      setPassword('');
      onAuthenticated(profile);
    } catch (err) {
      // Sur cet écran, un 401 signifie « identifiants incorrects » et non
      // « session expirée » : on affiche le message du backend.
      if (err.status === 401) {
        setError(err.message || 'Email ou mot de passe incorrect.');
      } else {
        setError(describeError(err, 'Connexion impossible pour le moment.'));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-box">
      <h1 className="auth-title">Connexion</h1>
      <p className="auth-subtitle">
        Accédez au suivi de vos projets, à vos livrables et à vos échanges.
      </p>

      {error && <div className="alert alert-danger">{error}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="email">Adresse email</label>
          <input
            id="email"
            type="email"
            required
            autoComplete="username"
            placeholder="nom@exemple.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        <div className="form-group">
          <label htmlFor="password">Mot de passe</label>
          <input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        <button
          type="submit"
          className="btn btn-primary btn-block"
          style={{ marginTop: '1rem' }}
          disabled={submitting}
        >
          {submitting ? 'Connexion...' : 'Se connecter'}
        </button>
      </form>

      <p className="auth-help">
        Pas encore de compte ? Les accès sont créés par votre prestataire :
        contactez-le pour recevoir vos identifiants.
      </p>
    </div>
  );
}
