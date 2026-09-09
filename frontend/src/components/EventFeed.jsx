import React from 'react';
import { displayName, eventTypeLabel, formatDateTime } from '../utils/format';

/**
 * Journal d'activité d'un projet. Les 50 derniers événements sont déjà inclus
 * dans la réponse détaillée du projet : pas d'appel supplémentaire nécessaire.
 */
export default function EventFeed({ events }) {
  const items = events || [];

  return (
    <section>
      <h2 className="section-title">
        Journal d’activité <span className="section-count">{items.length}</span>
      </h2>

      {items.length > 0 ? (
        <ul className="timeline">
          {items.map((event) => (
            <li key={event.id} className="timeline-item">
              <span className="timeline-type">{eventTypeLabel(event.type)}</span>
              <div className="timeline-body">
                <p className="timeline-summary">{event.summary}</p>
                <p className="timeline-meta">
                  {displayName(event.actor)} · {formatDateTime(event.created_at)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty-state">Aucun événement enregistré pour ce projet.</div>
      )}
    </section>
  );
}
