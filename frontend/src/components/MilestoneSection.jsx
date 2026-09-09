import React, { useState } from 'react';
import { api, describeError } from '../api';
import {
  formatDate,
  milestoneBadgeClass,
  milestoneStatusLabel,
  MILESTONE_STATUSES,
} from '../utils/format';

/**
 * Jalons d'un projet. Lecture pour tous ; création, changement de statut et
 * suppression réservés au prestataire (le backend exige `get_current_admin`).
 */
export default function MilestoneSection({ project, isAdmin, onChanged }) {
  const milestones = project.milestones || [];
  const done = milestones.filter((milestone) => milestone.status === 'fait').length;

  const [title, setTitle] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleCreate(event) {
    event.preventDefault();
    if (!title.trim()) return;
    setError('');
    setBusy(true);
    try {
      await api.createMilestone(project.id, {
        title: title.trim(),
        due_date: dueDate || null,
      });
      setTitle('');
      setDueDate('');
      await onChanged();
    } catch (err) {
      setError(describeError(err, 'Impossible d’ajouter ce jalon.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleStatusChange(milestone, status) {
    setError('');
    setBusy(true);
    try {
      await api.updateMilestone(project.id, milestone.id, { status });
      await onChanged();
    } catch (err) {
      setError(describeError(err, 'Impossible de mettre à jour ce jalon.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(milestone) {
    if (!window.confirm(`Supprimer le jalon « ${milestone.title} » ?`)) return;
    setError('');
    setBusy(true);
    try {
      await api.deleteMilestone(project.id, milestone.id);
      await onChanged();
    } catch (err) {
      setError(describeError(err, 'Impossible de supprimer ce jalon.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 className="section-title">
        Jalons{' '}
        <span className="section-count">
          {milestones.length > 0 ? `${done}/${milestones.length} terminés` : '0'}
        </span>
      </h2>

      {error && <div className="alert alert-danger">{error}</div>}

      {milestones.length > 0 ? (
        <ul className="milestone-list">
          {milestones.map((milestone) => (
            <li key={milestone.id} className="milestone-item">
              <div className="milestone-main">
                <span
                  className={`milestone-dot ${milestone.status === 'fait' ? 'is-done' : ''}`}
                  aria-hidden="true"
                />
                <div>
                  <div className="milestone-title">{milestone.title}</div>
                  <div className="milestone-meta">
                    {milestone.due_date
                      ? `Échéance : ${formatDate(milestone.due_date)}`
                      : 'Sans échéance'}
                  </div>
                </div>
              </div>

              <div className="milestone-actions">
                {isAdmin ? (
                  <>
                    <select
                      className="select-sm"
                      value={milestone.status}
                      disabled={busy}
                      aria-label={`Statut du jalon ${milestone.title}`}
                      onChange={(event) => handleStatusChange(milestone, event.target.value)}
                    >
                      {MILESTONE_STATUSES.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <button
                      className="btn btn-danger btn-sm"
                      disabled={busy}
                      onClick={() => handleDelete(milestone)}
                    >
                      Supprimer
                    </button>
                  </>
                ) : (
                  <span className={`badge ${milestoneBadgeClass(milestone.status)}`}>
                    {milestoneStatusLabel(milestone.status)}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty-state">
          {isAdmin
            ? 'Aucun jalon défini. Ajoutez les grandes étapes du projet ci-dessous.'
            : 'Aucun jalon n’a encore été défini pour ce projet.'}
        </div>
      )}

      {isAdmin && (
        <form className="inline-form" onSubmit={handleCreate}>
          <input
            type="text"
            placeholder="Nouvelle étape (ex : Maquettes validées)"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            aria-label="Titre du nouveau jalon"
          />
          <input
            type="date"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
            aria-label="Échéance du nouveau jalon"
          />
          <button type="submit" className="btn btn-secondary btn-sm" disabled={busy || !title.trim()}>
            Ajouter
          </button>
        </form>
      )}
    </section>
  );
}
