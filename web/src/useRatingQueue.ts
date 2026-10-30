import { useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from './api'
import type { QueueJob, Status, Track } from './api'

type Entry = {
  requestId: string; trackId: string; title: string; stars: number; expectedRevision: string;
  libraryScope: string; chosenAt: number; accepted: boolean; submitted: boolean; failed: boolean;
}
type Callbacks = {
  onConfirmed: (job: QueueJob) => void;
  onError: (error: unknown, scope: string) => void;
  onUpdated: () => void;
  onRecovered: (message: string) => void;
}

function readCache(key: string): Entry[] {
  const value: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
  if (!Array.isArray(value) || value.some(item => !item || typeof item.requestId !== 'string'
    || typeof item.trackId !== 'string' || typeof item.title !== 'string' || typeof item.expectedRevision !== 'string'
    || typeof item.libraryScope !== 'string' || !Number.isInteger(item.stars) || item.stars < 0 || item.stars > 5
    || typeof item.accepted !== 'boolean' || typeof item.submitted !== 'boolean' || typeof item.failed !== 'boolean'
    || typeof item.chosenAt !== 'number' || !Number.isFinite(item.chosenAt))) {
    throw new Error('Die vorgemerkten Bewertungen im Browser konnten nicht gelesen werden.')
  }
  return value as Entry[]
}

export function useRatingQueue(status: Status | null, callbacks: Callbacks) {
  const scope = status?.libraryScope ?? ''
  const mode = status?.mode ?? 'music'
  const key = status?.serverId && scope ? `itunesremote-rating-queue:${status.serverId}:${mode}:${scope}` : ''
  const [entries, setEntries] = useState<Entry[]>([])
  const current = useRef<Entry[]>([])
  const actions = useRef<{ key: string; save: (items: Entry[]) => void; removed: Set<string> } | null>(null)
  const handlers = useRef(callbacks)
  handlers.current = callbacks

  useEffect(() => {
    current.current = []
    setEntries([])
    if (!key) return
    let alive = true
    let syncing = false
    let lastPoll = 0
    let connectionError = ''
    let retryAt = 0
    let storageError = false
    const reported = new Set<string>()
    const removed = new Set<string>()
    function report(error: unknown) {
      if (alive) handlers.current.onError(error, scope)
    }
    function save(next: Entry[]) {
      if (!alive) return
      try {
        // Merge other tabs' outbox entries; terminal IDs stay removed in this tab.
        const merged = new Map(readCache(key).map(item => [item.requestId, item]))
        for (const item of next) merged.set(item.requestId, item)
        for (const id of removed) merged.delete(id)
        next = [...merged.values()]
        localStorage.setItem(key, JSON.stringify(next))
      } catch (error) {
        if (!storageError) report(error)
        storageError = true
      }
      current.current = next
      setEntries(next)
    }
    actions.current = { key, save, removed }
    try {
      current.current = readCache(key)
      setEntries(current.current)
    } catch (error) { report(error) }

    function merge(jobs: QueueJob[]) {
      let next = [...current.current]
      let updated = false
      for (const job of jobs) {
        if (job.libraryScope !== scope || job.mode !== mode) continue
        const known = next.find(item => item.requestId === job.requestId)
        if (job.state === 'confirmed' || job.state === 'superseded' || job.state === 'dismissed') {
          if (known && job.state === 'confirmed' && job.result && 'track' in job.result) {
            handlers.current.onConfirmed(job)
            updated = true
          }
          removed.add(job.requestId)
          next = next.filter(item => item.requestId !== job.requestId)
        } else {
          const entry: Entry = {
            requestId: job.requestId, trackId: job.trackId, title: job.title, stars: job.stars,
            libraryScope: scope, chosenAt: job.chosenAt, expectedRevision: known?.expectedRevision ?? '',
            accepted: true, submitted: true, failed: job.state === 'failed',
          }
          next = [...next.filter(item => item.requestId !== job.requestId), entry]
          if (entry.failed && !reported.has(job.requestId) && job.result && 'error' in job.result) {
            reported.add(job.requestId)
            const error = job.result.error
            report(new ApiError(error.code, `„${job.title}“: ${error.message}`, error.details))
          }
        }
      }
      save(next)
      if (updated) handlers.current.onUpdated()
    }

    async function tick() {
      if (!alive || syncing || Date.now() < retryAt) return
      syncing = true
      try {
        const outgoing = current.current.filter(item => !item.accepted && !item.failed).slice(0, 25)
        if (outgoing.length) {
          const ids = new Set(outgoing.map(item => item.requestId))
          save(current.current.map(item => ids.has(item.requestId) ? { ...item, submitted: true } : item))
          try {
            const result = await api<{ items: QueueJob[] }>('rating-queue', 'POST', {
              libraryScope: scope,
              items: outgoing.map(item => ({
                trackId: item.trackId, stars: item.stars, requestId: item.requestId,
                expectedRevision: item.expectedRevision, chosenAt: item.chosenAt,
              })),
            })
            if (!alive) return
            merge(result.items)
            if (connectionError) handlers.current.onRecovered(connectionError)
            connectionError = ''
          } catch (error) {
            if (!alive) return
            if (error instanceof ApiError && !['OFFLINE', 'HTTP_ERROR', 'LIBRARY_BUSY'].includes(error.code)) {
              save(current.current.map(item => ids.has(item.requestId) ? { ...item, failed: true } : item))
            }
            throw error
          }
        }
        if (!current.current.some(item => !item.failed) && Date.now() - lastPoll < 5000) return
        const ids = current.current.map(item => item.requestId)
        for (let offset = 0; offset < Math.max(ids.length, 1); offset += 100) {
          const params = new URLSearchParams({ mode, libraryScope: scope, ids: ids.slice(offset, offset + 100).join(',') })
          const result = await api<{ items: QueueJob[]; missingIds?: string[] }>(`rating-queue?${params}`)
          if (!alive) return
          merge(result.items)
          const missing = new Set(result.missingIds ?? [])
          if (current.current.some(item => item.accepted && missing.has(item.requestId))) {
            save(current.current.map(item => item.accepted && missing.has(item.requestId)
              ? { ...item, accepted: false, failed: true } : item))
            report(new ApiError('QUEUE_RESULT_MISSING', 'Die Bestätigung einer älteren Sitzung fehlt. Bitte prüfe die Bewertung.'))
          }
        }
        lastPoll = Date.now()
        if (connectionError) handlers.current.onRecovered(connectionError)
        connectionError = ''
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Die Warteschlange ist nicht erreichbar.'
        const transient = error instanceof ApiError && ['OFFLINE', 'HTTP_ERROR', 'LIBRARY_BUSY'].includes(error.code)
        if (message !== connectionError) report(error)
        connectionError = transient ? message : ''
        retryAt = Date.now() + 2000
      } finally { syncing = false }
    }
    void tick()
    const timer = window.setInterval(() => void tick(), 500)
    const wake = () => { if (!document.hidden) { retryAt = 0; void tick() } }
    const changed = (event: StorageEvent) => {
      if (event.key === key) {
        try {
          const combined = new Map(current.current.map(item => [item.requestId, item]))
          for (const entry of readCache(key)) combined.set(entry.requestId, entry)
          for (const id of removed) combined.delete(id)
          current.current = [...combined.values()]
          setEntries(current.current)
        } catch (error) { report(error) }
        void tick()
      }
    }
    window.addEventListener('online', wake)
    document.addEventListener('visibilitychange', wake)
    window.addEventListener('storage', changed)
    return () => {
      alive = false
      actions.current = null
      window.clearInterval(timer)
      window.removeEventListener('online', wake)
      document.removeEventListener('visibilitychange', wake)
      window.removeEventListener('storage', changed)
    }
  }, [key, mode, scope])

  function enqueue(track: Track, stars: number) {
    const action = actions.current
    if (!key || action?.key !== key) return
    // getRandomValues also works over HTTP on LAN addresses, unlike randomUUID.
    const requestId = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
    let chosenAt = Date.now()
    try {
      const previous = Number(localStorage.getItem(`${key}:last-choice`) ?? 0)
      if (Number.isFinite(previous)) chosenAt = Math.max(chosenAt, previous + 1)
      localStorage.setItem(`${key}:last-choice`, String(chosenAt))
    } catch (error) { handlers.current.onError(error, scope) }
    const next = current.current.filter(item => {
      if (item.trackId === track.id && (item.failed || !item.submitted)) {
        action.removed.add(item.requestId)
        return false
      }
      return true
    })
    action.save([...next, {
      requestId, trackId: track.id, title: track.title, stars, expectedRevision: track.ratingRevision,
      libraryScope: scope, chosenAt, accepted: false, submitted: false, failed: false,
    }])
  }

  async function dismissErrors() {
    const action = actions.current
    if (!action || action.key !== key) return
    for (const entry of current.current.filter(item => item.failed)) {
      if (entry.accepted) {
        try { await api(`rating-queue/${encodeURIComponent(entry.requestId)}/dismiss`, 'POST') }
        catch (error) {
          if (!(error instanceof ApiError && error.code === 'REQUEST_NOT_FOUND')) {
            handlers.current.onError(error, scope)
            continue
          }
        }
      }
      action.removed.add(entry.requestId)
      action.save(current.current.filter(item => item.requestId !== entry.requestId))
    }
  }

  const active = entries.filter(item => item.libraryScope === scope && !item.failed)
  const pendingStars = useMemo(() => {
    const result = new Map<string, number>()
    for (const entry of [...entries].filter(item => item.libraryScope === scope && !item.failed)
      .sort((first, second) => first.chosenAt - second.chosenAt)) result.set(entry.trackId, entry.stars)
    return result
  }, [entries, scope])
  return {
    enqueue, dismissErrors, pendingStars, pendingCount: active.length,
    uploadingCount: active.filter(item => !item.accepted).length,
    failedCount: entries.filter(item => item.libraryScope === scope && item.failed).length,
    failedTitles: [...new Set(entries.filter(item => item.libraryScope === scope && item.failed).map(item => item.title))],
  }
}
