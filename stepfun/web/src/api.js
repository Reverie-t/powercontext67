async function request(url, options) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(body.error || `${response.status} ${url}`);
  }
  return body;
}

export const api = {
  health() {
    return request("/api/health");
  },
  list() {
    return request("/api/collections");
  },
  create(name, dimension) {
    return request("/api/collections", {
      method: "POST",
      body: JSON.stringify({ name, dimension }),
    });
  },
  remove(name) {
    return request(`/api/collections/${name}`, { method: "DELETE" });
  },
  info(name) {
    return request(`/api/collections/${name}`);
  },
  add(name, payload) {
    return request(`/api/collections/${name}/documents`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  refresh(name) {
    return request(`/api/collections/${name}/refresh`, { method: "POST", body: "{}" });
  },
  search(name, payload) {
    return request(`/api/collections/${name}/search`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
