const TOKEN_KEY = 'portail_client_token';

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

async function request(endpoint, options = {}) {
  const token = getToken();
  const headers = {
    ...(options.headers || {}),
  };

  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // If body is an object (and not FormData), stringify to JSON and set Content-Type
  let body = options.body;
  if (body && !(body instanceof FormData) && typeof body === 'object') {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }

  const response = await fetch(endpoint, {
    ...options,
    headers,
    body,
  });

  if (response.status === 401) {
    clearToken();
  }

  if (!response.ok) {
    let errorDetail = 'Une erreur est survenue';
    try {
      const errData = await response.json();
      errorDetail = errData.detail || JSON.stringify(errData);
    } catch {
      errorDetail = `Erreur HTTP ${response.status}: ${response.statusText}`;
    }
    const error = new Error(errorDetail);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export const api = {
  // Auth
  async login(email, password) {
    const data = await request('/api/auth/login', {
      method: 'POST',
      body: { email, password },
    });
    if (data.access_token) {
      setToken(data.access_token);
    }
    return data;
  },

  async register(email, password) {
    return request('/api/auth/register', {
      method: 'POST',
      body: { email, password },
    });
  },

  async getMe() {
    return request('/api/auth/me');
  },

  logout() {
    clearToken();
  },

  async checkHealth() {
    return request('/health');
  },

  // Projects
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

  // Documents
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
    const response = await fetch(`/api/projects/${projectId}/documents/${documentId}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

    if (!response.ok) {
      throw new Error('Impossible de télécharger le document');
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
};
