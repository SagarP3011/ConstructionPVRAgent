/** Health check client for `GET /api/health`. */

export interface HealthResponse {
  status: string;
  version: string;
  data_dir_found: boolean;
  golden_found: boolean;
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch("/api/health", { signal });
  if (!response.ok) throw new Error(`Health check failed: HTTP ${response.status}`);
  return (await response.json()) as HealthResponse;
}
