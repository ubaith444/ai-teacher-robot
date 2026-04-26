export const API_BASE_URL = 'http://localhost:8000';

export const apiFetch = async (endpoint: string, options: RequestInit = {}) => {
  const token = localStorage.getItem('zoro_token');
  
  const headers: Record<string, string> = {
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...((options.headers as any) || {}),
  };

  // Only add Content-Type if not sending FormData
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_BASE_URL}/api${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    localStorage.removeItem('zoro_token');
    // window.location.href = '/login'; // Prevent infinite redirects if on login
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || response.statusText);
  }

  return response.json();
};

export const authApi = {
  login: async (credentials: any) => {
    const formData = new URLSearchParams();
    formData.append('username', credentials.username);
    formData.append('password', credentials.password);

    // Auth is included under /api prefix in main.py
    return fetch(`${API_BASE_URL}/api/auth/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Login failed');
      }
      return res.json();
    });
  },
};

export const studentApi = {
  list: (params: any = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiFetch(`/students/?${query}`);
  },
  enroll: (formData: FormData) => {
    return apiFetch('/students/enroll', {
      method: 'POST',
      body: formData,
    });
  },
};

export const attendanceApi = {
  getToday: (params: any = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiFetch(`/attendance/today?${query}`);
  },
  getReport: (params: any = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiFetch(`/attendance/report?${query}`);
  },
};

export const robotApi = {
  getStatus: () => {
    // Health is usually at /health or /api/robot/status
    return apiFetch('/robot/status');
  },
  control: (command: any) => apiFetch('/robot/command', {
    method: 'POST',
    body: JSON.stringify(command),
  }),
  getQuota: (sessionId: string) => apiFetch(`/v1/robot/quota/${sessionId}`),
};

export const syllabusApi = {
  upload: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiFetch('/syllabus/upload', {
      method: 'POST',
      body: formData,
    });
  },
  getStats: () => apiFetch('/syllabus/stats'),
};
