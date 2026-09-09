import React, { useCallback, useEffect, useState } from 'react';
import { api, describeError } from '../api';
import { displayName, formatDateTime, initials } from '../utils/format';

const MAX_LENGTH = 5000;

/** Fil de discussion d'un projet, ouvert au prestataire comme au client. */
export default function MessageThread({ projectId, user, onPosted }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setMessages(await api.getMessages(projectId));
    } catch (err) {
      setError(describeError(err, 'Impossible de charger les messages.'));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSubmit(event) {
    event.preventDefault();
    const trimmed = body.trim();
    if (!trimmed) return;

    setError('');
    setSending(true);
    try {
      const message = await api.createMessage(projectId, trimmed);
      setMessages((previous) => [...previous, message]);
      setBody('');
      if (onPosted) onPosted();
    } catch (err) {
      setError(describeError(err, 'Impossible d’envoyer votre message.'));
    } finally {
      setSending(false);
    }
  }

  return (
    <section>
      <h2 className="section-title">
        Messages <span className="section-count">{messages.length}</span>
      </h2>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="empty-state">Chargement des messages...</div>
      ) : messages.length > 0 ? (
        <ul className="message-thread">
          {messages.map((message) => {
            const isMine = message.author?.id === user.id;
            return (
              <li key={message.id} className={`message ${isMine ? 'is-mine' : ''}`}>
                <span
                  className={`avatar ${message.author?.role === 'admin' ? 'avatar-admin' : ''}`}
                  aria-hidden="true"
                >
                  {initials(message.author)}
                </span>
                <div className="message-bubble">
                  <div className="message-head">
                    <span className="message-author">
                      {isMine ? 'Vous' : displayName(message.author)}
                    </span>
                    <span className="message-date">{formatDateTime(message.created_at)}</span>
                  </div>
                  <p className="message-body">{message.body}</p>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="empty-state">
          Aucun message pour l’instant. Lancez la conversation ci-dessous.
        </div>
      )}

      <form className="message-form" onSubmit={handleSubmit}>
        <label htmlFor="new-message">Écrire un message</label>
        <textarea
          id="new-message"
          rows="3"
          maxLength={MAX_LENGTH}
          placeholder="Votre message..."
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
        <div className="message-form-actions">
          <span className="field-hint">
            {body.length}/{MAX_LENGTH} caractères
          </span>
          <button type="submit" className="btn btn-primary btn-sm" disabled={sending || !body.trim()}>
            {sending ? 'Envoi...' : 'Envoyer'}
          </button>
        </div>
      </form>
    </section>
  );
}
