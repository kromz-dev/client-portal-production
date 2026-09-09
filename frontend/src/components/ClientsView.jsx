import React, { useCallback, useEffect, useState } from 'react';
import Modal from './Modal';
import { api, describeError } from '../api';
import { formatDate, plural } from '../utils/format';

const MIN_PASSWORD_LENGTH = 8;

function CreateClientModal({ onClose, onCreated }) {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Le mot de passe doit contenir au moins ${MIN_PASSWORD_LENGTH} caractères.`);
      return;
    }

    setSubmitting(true);
    try {
      const client = await api.createClient({
        email: email.trim(),
        full_name: fullName.trim(),
        password,
      });
      onCreated(client);
      onClose();
    } catch (err) {
      setError(describeError(err, 'Impossible de créer ce compte client.'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title="Nouveau compte client" onClose={onClose}>
      {error && <div className="alert alert-danger">{error}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="client-name">Nom du client</label>
          <input
            id="client-name"
            type="text"
            required
            placeholder="ex : Sophie Martin, Boulangerie Durand..."
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />
        </div>

        <div className="form-group">
          <label htmlFor="client-email">Adresse email</label>
          <input
            id="client-email"
            type="email"
            required
            placeholder="client@exemple.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <span className="field-hint">Elle servira d’identifiant de connexion.</span>
        </div>

        <div className="form-group">
          <label htmlFor="client-password">Mot de passe provisoire</label>
          <input
            id="client-password"
            type="text"
            required
            minLength={MIN_PASSWORD_LENGTH}
            autoComplete="off"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <span className="field-hint">
            {MIN_PASSWORD_LENGTH} caractères minimum. Transmettez-le au client : il pourra le
            changer depuis son espace.
          </span>
        </div>

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Annuler
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Création...' : 'Créer le compte'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Espace « Clients » du prestataire : liste et création de comptes. */
export default function ClientsView({ onNotify }) {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setClients(await api.getClients());
    } catch (err) {
      setError(describeError(err, 'Impossible de charger la liste des clients.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function handleCreated(client) {
    onNotify(`Le compte de ${client.full_name || client.email} a été créé.`);
    load();
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Clients</h1>
          <p className="page-subtitle">
            Créez les accès de vos clients et suivez le nombre de projets qui leur sont rattachés.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setModalOpen(true)}>
          + Nouveau client
        </button>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="empty-state">Chargement des clients...</div>
      ) : clients.length > 0 ? (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Nom</th>
                <th>Email</th>
                <th>Projets</th>
                <th>Compte créé le</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((client) => (
                <tr key={client.id}>
                  <td>{client.full_name || <span className="muted">Non renseigné</span>}</td>
                  <td>{client.email}</td>
                  <td>{plural(client.project_count ?? 0, 'projet')}</td>
                  <td>{formatDate(client.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-state">
          <p style={{ marginBottom: '1rem' }}>Aucun compte client pour le moment.</p>
          <button className="btn btn-primary btn-sm" onClick={() => setModalOpen(true)}>
            Créer le premier compte client
          </button>
        </div>
      )}

      {modalOpen && (
        <CreateClientModal onClose={() => setModalOpen(false)} onCreated={handleCreated} />
      )}
    </div>
  );
}
