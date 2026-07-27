export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers =
    init.body instanceof FormData
      ? { ...(init.headers || {}) }
      : { "Content-Type": "application/json", ...(init.headers || {}) };
  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Não foi possível concluir a solicitação.");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
