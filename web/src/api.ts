export type Track = {
  id: string; title: string; artist: string; album: string; albumArtist: string; genre: string;
  year: number | null; durationSeconds: number; ratingRaw: number;
  ratingOrigin: 'none' | 'user' | 'album'; ratingRevision: string;
  ratingCapability: 'unknown' | 'writable' | 'unavailable'; capabilityReason: string | null;
  playCount: number; lastPlayed: string | null; addedDate: string | null; isCloud: boolean; hasArtwork: boolean;
}
export type Playlist = { id: string; name: string; trackCount: number; isMaster: boolean }
export type LibraryProgress = {
  stage: string; completed: number; total: number; sequence: number; runId: string;
  elapsedSeconds: number; stageElapsedSeconds: number; idleSeconds: number;
}
export type Status = {
  serverId: string; mode: 'music' | 'demo'; connected: boolean; refreshing: boolean; hasCache: boolean;
  progress: LibraryProgress | null;
  libraryScope: string | null; snapshotRevision: string | null; lastSyncedAt: string | null;
  counts: { total: number; rated: number; unrated: number };
  error: { code: string; message: string; details: Record<string, unknown> } | null;
}
export type TrackPage = { items: Track[]; total: number; nextCursor: string | null; libraryScope: string | null; snapshotRevision: string }
export type RatingResult = { track: Track; requestId: string; libraryScope: string; state: 'confirmed' }
export type QueueJob = {
  requestId: string; trackId: string; title: string; stars: number; libraryScope: string; mode: 'music' | 'demo';
  state: 'queued' | 'running' | 'confirmed' | 'failed' | 'superseded' | 'dismissed';
  createdAt: number; updatedAt: number; chosenAt: number;
  result: RatingResult | { error: { code: string; message: string; details: Record<string, unknown> } } | null;
}
export type Device = { id: string; name: string }
export type DeviceTokens = { deviceId: string; accessToken: string; refreshToken: string; expiresIn: number }
export type PermissionResult = {
  mode: 'music' | 'demo'; needsSettings: boolean; libraryConnected: boolean;
  media: { status: string; message: string }; automation: { status: string; message: string };
  libraryError?: { message: string };
}

export class ApiError extends Error {
  code: string
  details: Record<string, unknown>
  constructor(code: string, message: string, details: Record<string, unknown> = {}) {
    super(message); this.code = code; this.details = details
  }
}

let csrf = ''
let initialization: Promise<void> | null = null

export async function api<T>(path: string, method = 'GET', data?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/v1/${path}`, {
      method, signal, credentials: 'same-origin',
      headers: method === 'GET' ? {} : { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: method === 'GET' ? undefined : JSON.stringify(data ?? {}),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('OFFLINE', 'Der Mac ist gerade nicht erreichbar. Dein letzter Stand bleibt sichtbar.')
  }
  const result = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(result?.error?.code ?? 'HTTP_ERROR', result?.error?.message ?? 'Die Anfrage konnte nicht ausgeführt werden.', result?.error?.details)
  }
  return result as T
}

export function initializeSession(): Promise<void> {
  if (!initialization) initialization = (async () => {
    const params = new URLSearchParams(location.hash.slice(1))
    const code = params.get('code')
    history.replaceState(null, '', location.pathname)
    if (code) {
      const result = await api<{ csrfToken: string }>('auth/exchange', 'POST', { code })
      csrf = result.csrfToken
    } else {
      const result = await api<{ csrfToken: string }>('auth/session')
      csrf = result.csrfToken
    }
  })()
  return initialization
}

export async function loginSession(password: string): Promise<void> {
  const result = await api<{ csrfToken: string }>('auth/login', 'POST', { password })
  csrf = result.csrfToken
  initialization = Promise.resolve()
}

export async function logoutSession(): Promise<void> {
  await api('auth/logout', 'POST')
  csrf = ''
  initialization = null
}
