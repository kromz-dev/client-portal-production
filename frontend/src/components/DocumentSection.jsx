import React, { useRef, useState } from 'react';
import { api, describeError } from '../api';
import {
  documentKindLabel,
  formatDate,
  formatDateTime,
  reviewBadgeClass,
  reviewLabel,
} from '../utils/format';

function DocumentIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ color: 'var(--primary)', flexShrink: 0 }}
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

/**
 * Documents d'un projet.
 * - Le dépôt est ouvert aux deux rôles : le backend marque le fichier
 *   « livrable » côté prestataire et « pièce client » côté client.
 * - La revue d'un livrable est réservée au client (403 sinon).
 * - Un client ne peut supprimer que ses propres pièces.
 */
export default function DocumentSection({ project, user, onChanged }) {
  const documents = project.documents || [];
  const isAdmin = user.role === 'admin';

  const fileInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [reviewingId, setReviewingId] = useState(null);
  const [reviewComment, setReviewComment] = useState('');
  const [busy, setBusy] = useState(false);

  function canDelete(doc) {
    if (isAdmin) return true;
    return doc.kind === 'piece_client' && doc.uploaded_by === user.id;
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError('');
    setUploading(true);
    try {
      await api.uploadDocument(project.id, file);
      await onChanged();
    } catch (err) {
      setError(describeError(err, 'Impossible d’envoyer ce document.'));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function handleDownload(doc) {
    setError('');
    try {
      await api.downloadDocument(project.id, doc.id, doc.filename);
    } catch (err) {
      setError(describeError(err, 'Impossible de télécharger ce document.'));
    }
  }

  async function handleDelete(doc) {
    if (!window.confirm(`Supprimer le document « ${doc.filename} » ?`)) return;
    setError('');
    setBusy(true);
    try {
      await api.deleteDocument(project.id, doc.id);
      await onChanged();
    } catch (err) {
      setError(describeError(err, 'Impossible de supprimer ce document.'));
    } finally {
      setBusy(false);
    }
  }

  async function handleReview(doc, decision) {
    setError('');
    setBusy(true);
    try {
      await api.reviewDocument(project.id, doc.id, decision, reviewComment.trim());
      setReviewingId(null);
      setReviewComment('');
      await onChanged();
    } catch (err) {
      setError(describeError(err, 'Impossible d’enregistrer votre revue.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 className="section-title">
        Documents <span className="section-count">{documents.length}</span>
      </h2>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="upload-zone">
        <input type="file" ref={fileInputRef} style={{ display: 'none' }} onChange={handleUpload} />
        <p style={{ marginBottom: '0.75rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
          {isAdmin
            ? 'Déposez un livrable destiné au client (PDF, image, document bureautique...).'
            : 'Déposez une pièce pour votre prestataire (PDF, image, document bureautique...).'}
        </p>
        <button
          className="btn btn-secondary btn-sm"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? 'Envoi en cours...' : 'Choisir un fichier'}
        </button>
      </div>

      {documents.length > 0 ? (
        <ul className="doc-list">
          {documents.map((doc) => {
            const isDeliverable = doc.kind === 'livrable';
            const canReview = !isAdmin && isDeliverable;

            return (
              <li key={doc.id} className="doc-item">
                <div className="doc-row">
                  <div className="doc-info">
                    <DocumentIcon />
                    <div>
                      <div className="doc-name">{doc.filename}</div>
                      <div className="doc-date">
                        {documentKindLabel(doc.kind)} · déposé le {formatDate(doc.uploaded_at)}
                      </div>
                      {isDeliverable && (
                        <div className="doc-review">
                          <span className={`badge ${reviewBadgeClass(doc.review_status)}`}>
                            {reviewLabel(doc.review_status)}
                          </span>
                          {doc.reviewed_at && (
                            <span className="doc-date"> le {formatDateTime(doc.reviewed_at)}</span>
                          )}
                          {doc.review_comment && (
                            <p className="doc-comment">« {doc.review_comment} »</p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="doc-actions">
                    <button className="btn btn-secondary btn-sm" onClick={() => handleDownload(doc)}>
                      Télécharger
                    </button>
                    {canReview && (
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={busy}
                        onClick={() => {
                          setReviewingId(reviewingId === doc.id ? null : doc.id);
                          setReviewComment(doc.review_comment || '');
                        }}
                      >
                        {doc.review_status ? 'Revoir' : 'Donner mon avis'}
                      </button>
                    )}
                    {canDelete(doc) && (
                      <button
                        className="btn btn-danger btn-sm"
                        disabled={busy}
                        onClick={() => handleDelete(doc)}
                      >
                        Supprimer
                      </button>
                    )}
                  </div>
                </div>

                {canReview && reviewingId === doc.id && (
                  <div className="review-form">
                    <label htmlFor={`review-${doc.id}`}>Commentaire (facultatif)</label>
                    <textarea
                      id={`review-${doc.id}`}
                      rows="2"
                      maxLength={2000}
                      placeholder="Précisez ce qui convient ou ce qui doit être revu..."
                      value={reviewComment}
                      onChange={(event) => setReviewComment(event.target.value)}
                    />
                    <div className="review-actions">
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={busy}
                        onClick={() => setReviewingId(null)}
                      >
                        Annuler
                      </button>
                      <button
                        className="btn btn-danger btn-sm"
                        disabled={busy}
                        onClick={() => handleReview(doc, 'revision_demandee')}
                      >
                        Demander une révision
                      </button>
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={busy}
                        onClick={() => handleReview(doc, 'approuve')}
                      >
                        Approuver
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="empty-state">Aucun document n’a encore été déposé pour ce projet.</div>
      )}
    </section>
  );
}
