import React, { useEffect, useState } from 'react';
import Modal from './Modal';
import { api, describeError } from '../api';
import { PROJECT_STATUSES } from '../utils/format';

/**
 * Création et modification d'un projet (réservé au prestataire).
 * `project` non nul = mode édition.
 */
export default function ProjectFormModal({ project, onClose, onSaved }) {
  const isEdit = Boolean(project);

  const [title, setTitle] = useState(project?.title || '');
  const [description, setDescription] = useState(project?.description || '');
  const [status, setStatus] = useState(project?.status || 'En cours');
  const [clientId, setClientId] = useState(project?.client_id ? String(project.client_id) : '');
  const [startedAt, setStartedAt] = useState(project?.started_at || '');
  const [dueDate, setDueDate] = useState(project?.due_date || '');

  const [clients, setClients] = useState([]);
  const [clientsError, setClientsError] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadClients() {
      try {
        const data = await api.getClients();
        if (!cancelled) setClients(data);
      } catch (err) {
        if (!cancelled) {
          setClientsError(describeError(err, 'Impossible de charger la liste des clients.'));
        }
      }
    }
    loadClients();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');

    if (!title.trim()) {
      setError('Le titre du projet est obligatoire.');
      return;
    }
    if (!clientId) {
      setError('Sélectionnez le client destinataire du projet.');
      return;
    }

    const payload = {
      title: title.trim(),
      description: description.trim() || null,
      status,
      client_id: Number(clientId),
      started_at: startedAt || null,
      due_date: dueDate || null,
    };

    setSubmitting(true);
    try {
      const saved = isEdit
        ? await api.updateProject(project.id, payload)
        : await api.createProject(payload);
      onSaved(saved, isEdit);
      onClose();
    } catch (err) {
      setError(
        describeError(
          err,
          isEdit ? 'Impossible d’enregistrer les modifications.' : 'Impossible de créer le projet.',
        ),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title={isEdit ? 'Modifier le projet' : 'Nouveau projet'} onClose={onClose}>
      {error && <div className="alert alert-danger">{error}</div>}
      {clientsError && <div className="alert alert-danger">{clientsError}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="p-title">Titre du projet</label>
          <input
            id="p-title"
            type="text"
            required
            placeholder="ex : Refonte site web, Audit SEO..."
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>

        <div className="form-group">
          <label htmlFor="p-client">Client</label>
          <select
            id="p-client"
            required
            value={clientId}
            onChange={(event) => setClientId(event.target.value)}
          >
            <option value="">— Sélectionner un client —</option>
            {clients.map((client) => (
              <option key={client.id} value={client.id}>
                {client.full_name ? `${client.full_name} (${client.email})` : client.email}
              </option>
            ))}
          </select>
          {clients.length === 0 && !clientsError && (
            <span className="field-hint">
              Aucun client enregistré : créez d’abord un compte depuis l’onglet « Clients ».
            </span>
          )}
        </div>

        <div className="form-group">
          <label htmlFor="p-desc">Description</label>
          <textarea
            id="p-desc"
            rows="3"
            placeholder="Objectifs, détails, livrables attendus..."
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="p-status">Statut</label>
            <select
              id="p-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              {PROJECT_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="p-started">Date de démarrage</label>
            <input
              id="p-started"
              type="date"
              value={startedAt}
              onChange={(event) => setStartedAt(event.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="p-due">Échéance</label>
            <input
              id="p-due"
              type="date"
              value={dueDate}
              onChange={(event) => setDueDate(event.target.value)}
            />
          </div>
        </div>

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Annuler
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Enregistrement...' : isEdit ? 'Enregistrer' : 'Créer le projet'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
