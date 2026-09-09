const TOKEN_KEY = 'portail_client_token';

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

/**
 * Callback déclenché lorsqu'une requête authentifiée reçoit un 401 : le jeton
 * est expiré ou invalide, l'application doit revenir à l'écran de connexion.
 */
let unauthorizedHandler = null;
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

export class ApiError extends Error {
  constructor(message, status, { isNetworkError = false } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.isNetworkError = isNetworkError;
  }
}

/** Extrait un message lisible du corps d'erreur renvoyé par FastAPI. */
function readDetail(payload, response) {
  const detail = payload?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim();
  }
  // Erreurs de validation Pydantic : detail est une liste d'objets.
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item?.msg === 'string' ? item.msg : null))
      .filter(Boolean);
    if (messages.length > 0) {
      return messages.join(' ; ');
    }
  }
  return `Erreur HTTP ${response.status} : ${response.statusText || 'requête refusée'}`;
}

async function handleErrorResponse(response, { skipAuthHandler = false } = {}) {
  if (response.status === 401) {
    clearToken();
    if (!skipAuthHandler && typeof unauthorizedHandler === 'function') {
      unauthorizedHandler();
    }
  }

  let detail;
  try {
    detail = readDetail(await response.json(), response);
  } catch {
    detail = `Erreur HTTP ${response.status} : ${response.statusText || 'requête refusée'}`;
  }
  throw new ApiError(detail, response.status);
}

async function request(endpoint, options = {}) {
  const { skipAuthHandler = false, ...fetchOptions } = options;
  const token = getToken();
  const headers = {
    ...(fetchOptions.headers || {}),
  };

  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // If body is an object (and not FormData), stringify to JSON and set Content-Type
  let body = fetchOptions.body;
  if (body && !(body instanceof FormData) && typeof body === 'object') {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(endpoint, {
      ...fetchOptions,
      headers,
      body,
    });
  } catch {
    throw new ApiError(
      'Le serveur est injoignable. Vérifiez votre connexion puis réessayez.',
      0,
      { isNetworkError: true },
    );
  }

  if (!response.ok) {
    await handleErrorResponse(response, { skipAuthHandler });
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

/**
 * Traduit une erreur d'API en message compréhensible par un utilisateur non
 * technique. Le `detail` renvoyé par le backend est déjà rédigé en français :
 * on le privilégie, et on complète par un message générique par code HTTP.
 */
export function describeError(error, fallback = 'Une erreur est survenue. Veuillez réessayer.') {
  if (!error) return fallback;
  if (error.isNetworkError) {
    return 'Le serveur est injoignable. Vérifiez votre connexion puis réessayez.';
  }

  const detail = typeof error.message === 'string' ? error.message.trim() : '';

  switch (error.status) {
    case 401:
      return 'Votre session a expiré. Veuillez vous reconnecter.';
    case 403:
      return detail || "Vous n'avez pas les droits nécessaires pour cette action.";
    case 404:
      return detail || "Cet élément est introuvable : il a peut-être été supprimé entre-temps.";
    case 413:
      return detail || 'Ce fichier est trop volumineux.';
    case 415:
      return detail || "Ce type de fichier n'est pas accepté.";
    case 422:
      return detail || 'Certaines informations saisies ne sont pas valides.';
    case 429:
      return detail || 'Trop de tentatives. Patientez une minute puis réessayez.';
    default:
      if (typeof error.status === 'number' && error.status >= 500) {
        return 'Le serveur a rencontré un problème. Réessayez dans un instant.';
      }
      return detail || fallback;
  }
}

export const api = {
  // ==========================================================================
  // Auth
  // ==========================================================================
  async login(email, password) {
    const data = await request('/api/auth/login', {
      method: 'POST',
      body: { email, password },
      // Un 401 ici signifie « identifiants incorrects », pas « session expirée » :
      // on ne déclenche donc pas la déconnexion globale.
      skipAuthHandler: true,
    });
    if (data.access_token) {
      setToken(data.access_token);
    }
    return data;
  },

  async getMe() {
    return request('/api/auth/me');
  },

  async changePassword(currentPassword, newPassword) {
    return request('/api/auth/change-password', {
      method: 'POST',
      body: { current_password: currentPassword, new_password: newPassword },
      // Ici le 401 veut dire « mot de passe actuel incorrect » : on garde
      // l'utilisateur connecté et on affiche l'erreur dans le formulaire.
      skipAuthHandler: true,
    });
  },

  logout() {
    clearToken();
  },

  async checkHealth() {
    return request('/health');
  },

  // ==========================================================================
  // Clients (réservé au prestataire)
  // ==========================================================================
  async getClients() {
    return request('/api/clients');
  },

  async createClient(client) {
    return request('/api/clients', {
      method: 'POST',
      body: client,
    });
  },

  // ==========================================================================
  // Projects
  // ==========================================================================
  async getProjects() {
    return request('/api/projects');
  },

  async getProject(projectId) {
    return request(`/api/projects/${projectId}`);
  },

  async createProject(project) {
    return request('/api/projects', {
      method: 'POST',
      body: project,
    });
  },

  async updateProject(projectId, projectData) {
    return request(`/api/projects/${projectId}`, {
      method: 'PUT',
      body: projectData,
    });
  },

  async deleteProject(projectId) {
    return request(`/api/projects/${projectId}`, {
      method: 'DELETE',
    });
  },

  // ==========================================================================
  // Documents
  // ==========================================================================
  async uploadDocument(projectId, file) {
    const formData = new FormData();
    formData.append('file', file);
    return request(`/api/projects/${projectId}/documents`, {
      method: 'POST',
      body: formData,
    });
  },

  async downloadDocument(projectId, documentId, filename) {
    const token = getToken();
    let response;
    try {
      response = await fetch(`/api/projects/${projectId}/documents/${documentId}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      throw new ApiError(
        'Le serveur est injoignable. Vérifiez votre connexion puis réessayez.',
        0,
        { isNetworkError: true },
      );
    }

    // Cohérence avec le helper request() : purge du jeton sur 401 et
    // remontée du message « detail » renvoyé par le backend
    if (!response.ok) {
      await handleErrorResponse(response);
    }

    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = filename || 'document';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(downloadUrl);
  },

  async deleteDocument(projectId, documentId) {
    return request(`/api/projects/${projectId}/documents/${documentId}`, {
      method: 'DELETE',
    });
  },

  /** decision : 'approuve' | 'revision_demandee'. Réservé au client. */
  async reviewDocument(projectId, documentId, decision, comment) {
    return request(`/api/projects/${projectId}/documents/${documentId}/review`, {
      method: 'POST',
      body: { decision, comment: comment || null },
    });
  },

  // ==========================================================================
  // Messages
  // ==========================================================================
  async getMessages(projectId) {
    return request(`/api/projects/${projectId}/messages`);
  },

  async createMessage(projectId, body) {
    return request(`/api/projects/${projectId}/messages`, {
      method: 'POST',
      body: { body },
    });
  },

  // ==========================================================================
  // Événements (journal d'activité)
  // ==========================================================================
  async getEvents(projectId) {
    return request(`/api/projects/${projectId}/events`);
  },

  // ==========================================================================
  // Jalons (réservé au prestataire en écriture)
  // ==========================================================================
  async createMilestone(projectId, milestone) {
    return request(`/api/projects/${projectId}/milestones`, {
      method: 'POST',
      body: milestone,
    });
  },

  async updateMilestone(projectId, milestoneId, milestone) {
    return request(`/api/projects/${projectId}/milestones/${milestoneId}`, {
      method: 'PUT',
      body: milestone,
    });
  },

  async deleteMilestone(projectId, milestoneId) {
    return request(`/api/projects/${projectId}/milestones/${milestoneId}`, {
      method: 'DELETE',
    });
  },

  // ==========================================================================
  // Tableau de bord
  // ==========================================================================
  async getDashboard() {
    return request('/api/dashboard');
  },
};
