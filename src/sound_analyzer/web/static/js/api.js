const JSON_HEADERS = { Accept: "application/json" };

async function request(url, options = {}) {
  const response = await fetch(url, { headers: JSON_HEADERS, ...options });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && body.detail) detail = body.detail;
    } catch {
      /* the server did not answer JSON; keep the status line */
    }
    throw new Error(detail);
  }
  return response.json();
}

function qs(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, value);
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export const api = {
  library: () => request("/api/library"),
  browse: (params) => request(`/api/browse${qs(params)}`),
  search: (params) => request(`/api/search${qs(params)}`),
  searchAudio: (file, params) => {
    const body = new FormData();
    body.append("file", file);
    return request(`/api/search/audio${qs(params)}`, { method: "POST", body });
  },
  peaks: (id, buckets) => request(`/api/clip/${id}/peaks${qs({ buckets })}`),
  reveal: (clipId) =>
    request("/api/reveal", {
      method: "POST",
      headers: { ...JSON_HEADERS, "Content-Type": "application/json" },
      body: JSON.stringify({ clip_id: clipId }),
    }),
  audioUrl: (id) => `/api/clip/${id}/audio`,
  downloadUrl: (id) => `/api/clip/${id}/download`,
};
