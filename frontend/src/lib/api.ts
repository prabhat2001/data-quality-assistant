export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : response.statusText;
    throw new Error(message || "Request failed");
  }
  return body as T;
}
