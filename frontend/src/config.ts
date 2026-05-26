let apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

// If the API URL is set but doesn't start with http:// or https://, and is not a relative path starting with /,
// we assume it's a hostname (e.g. from Render's host property) and format it properly.
if (apiUrl && !apiUrl.startsWith('http://') && !apiUrl.startsWith('https://') && !apiUrl.startsWith('/')) {
  let hostname = apiUrl.endsWith('/') ? apiUrl.slice(0, -1) : apiUrl;
  
  // If the hostname is a private Render name (no dot, e.g. "gold-weight-api"), append the Render public domain suffix.
  if (!hostname.includes('.') && hostname !== 'localhost') {
    hostname = `${hostname}.onrender.com`;
  }
  
  apiUrl = `https://${hostname}`;
  if (!apiUrl.endsWith('/api/v1')) {
    apiUrl = `${apiUrl}/api/v1`;
  }
}

export const API_BASE_URL = apiUrl;


