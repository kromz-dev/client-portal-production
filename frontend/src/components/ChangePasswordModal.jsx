import React, { useState } from 'react';
import Modal from './Modal';
import { api, describeError } from '../api';

const MIN_LENGTH = 8;

export default function ChangePasswordModal({ onClose, onSuccess }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');

    if (newPassword.length < MIN_LENGTH) {
      setError(`Le nouveau mot de passe doit contenir au moins ${MIN_LENGTH} caractères.`);
      return;
    }
    if (newPassword !== confirmation) {
      setError('Les deux nouveaux mots de passe ne correspondent pas.');
      return;
    }

    setSubmitting(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      onSuccess('Votre mot de passe a bien été mis à jour.');
      onClose();
    } catch (err) {
      if (err.status === 401) {
        setError(err.message || 'Mot de passe actuel incorrect.');
      } else {
        setError(describeError(err, 'Impossible de modifier le mot de passe.'));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title="Changer mon mot de passe" onClose={onClose}>
      {error && <div className="alert alert-danger">{error}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="current-password">Mot de passe actuel</label>
          <input
            id="current-password"
            type="password"
            required
            autoComplete="current-password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
        </div>

        <div className="form-group">
          <label htmlFor="new-password">Nouveau mot de passe</label>
          <input
            id="new-password"
            type="password"
            required
            minLength={MIN_LENGTH}
            autoComplete="new-password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
          <span className="field-hint">{MIN_LENGTH} caractères minimum.</span>
        </div>

        <div className="form-group">
          <label htmlFor="confirm-password">Confirmer le nouveau mot de passe</label>
          <input
            id="confirm-password"
            type="password"
            required
            autoComplete="new-password"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
          />
        </div>

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Annuler
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Enregistrement...' : 'Mettre à jour'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
