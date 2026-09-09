// Helpers d'affichage partagés par les composants (dates, libellés, badges).

const DAY_ONLY = /^\d{4}-\d{2}-\d{2}$/;

/** Formate une date (« 2025-03-14 ») ou un instant ISO en jj/mm/aaaa. */
export function formatDate(value) {
  if (!value) return '';
  // Les champs `date` du backend sont des chaînes « AAAA-MM-JJ » : on les
  // formate à la main pour éviter le décalage de fuseau de `new Date()`.
  if (typeof value === 'string' && DAY_ONLY.test(value)) {
    const [year, month, day] = value.split('-');
    return `${day}/${month}/${year}`;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString('fr-FR');
}

/** Formate un instant ISO en « jj/mm/aaaa à hh:mm ». */
export function formatDateTime(value) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  const date = parsed.toLocaleDateString('fr-FR');
  const time = parsed.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  return `${date} à ${time}`;
}

/** Classe CSS du badge de statut d'un projet. */
export function statusBadgeClass(status) {
  if (status === 'Terminé') return 'badge-termine';
  if (status === 'En attente') return 'badge-en-attente';
  return 'badge-en-cours';
}

/** Nom affichable d'un acteur (auteur de message, acteur d'événement, client). */
export function displayName(actor) {
  if (!actor) return 'Utilisateur supprimé';
  return actor.full_name || actor.email;
}

/** Initiales pour l'avatar d'un message. */
export function initials(actor) {
  const name = displayName(actor);
  const parts = name.replace(/[^\p{L}\s@.]/gu, ' ').split(/[\s@.]+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export const PROJECT_STATUSES = ['En attente', 'En cours', 'Terminé'];

export const MILESTONE_STATUSES = [
  { value: 'a_faire', label: 'À faire' },
  { value: 'en_cours', label: 'En cours' },
  { value: 'fait', label: 'Fait' },
];

export function milestoneStatusLabel(status) {
  const found = MILESTONE_STATUSES.find((s) => s.value === status);
  return found ? found.label : status;
}

export function milestoneBadgeClass(status) {
  if (status === 'fait') return 'badge-termine';
  if (status === 'en_cours') return 'badge-en-cours';
  return 'badge-en-attente';
}

export function documentKindLabel(kind) {
  return kind === 'piece_client' ? 'Pièce client' : 'Livrable';
}

export function reviewLabel(status) {
  if (status === 'approuve') return 'Approuvé';
  if (status === 'revision_demandee') return 'Révision demandée';
  return 'En attente de revue';
}

export function reviewBadgeClass(status) {
  if (status === 'approuve') return 'badge-termine';
  if (status === 'revision_demandee') return 'badge-en-attente';
  return 'badge-neutre';
}

/** Libellé lisible du type d'un événement du journal. */
export function eventTypeLabel(type) {
  switch (type) {
    case 'statut':
      return 'Statut';
    case 'document':
      return 'Document';
    case 'revue':
      return 'Revue';
    case 'message':
      return 'Message';
    case 'jalon':
      return 'Jalon';
    default:
      return type;
  }
}

/** Accord singulier/pluriel simple : plural(2, 'document') -> '2 documents'. */
export function plural(count, singular, pluralForm) {
  const word = count > 1 ? pluralForm || `${singular}s` : singular;
  return `${count} ${word}`;
}
