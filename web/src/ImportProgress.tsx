import { useEffect, useMemo, useState } from 'react'
import { CheckCheck, LoaderCircle, X } from 'lucide-react'
import type { LibraryProgress, Status } from './api'

const number = new Intl.NumberFormat('de-DE')
const countedStages = new Set([
  'native-tracks', 'tracks', 'playlists', 'snapshot-tracks', 'snapshot-playlists',
  'ratings', 'indexing', 'index-serialize', 'index-playlists',
])

export function progressMessage(progress: LibraryProgress): string {
  const completed = number.format(progress.completed)
  const total = number.format(progress.total)
  const count = `${completed} von ${total}`
  switch (progress.stage) {
    case 'opening': return 'Musikbibliothek wird geöffnet …'
    case 'permission-check': return 'Medienfreigabe wird geprüft …'
    case 'native-open': return 'Musikschnittstelle öffnet die Bibliothek …'
    case 'native-reload': return 'Musikschnittstelle lädt die Bibliothek neu …'
    case 'native-playlists': return 'Playlistübersicht wird abgerufen …'
    case 'native-tracks': return progress.total > 0 ? `Titeleinträge abrufen: ${count}` : 'Titeleinträge werden abgerufen …'
    case 'tracks': return `Titel einlesen: ${count}`
    case 'playlists': return `Playlists einlesen: ${count}`
    case 'preparing': return 'Bibliotheksdaten werden vorbereitet …'
    case 'native-cleanup': return 'Native Bibliotheksobjekte werden aufgeräumt …'
    case 'snapshot-tracks': return `Titeldaten kopieren: ${count}`
    case 'snapshot-playlists': return `Playlistdaten kopieren: ${count}`
    case 'rating-index': return 'Bewertungsabgleich wird vorbereitet …'
    case 'ratings': return `Bewertungen abgleichen: ${count}`
    case 'indexing': return `Suchindex aufbauen: ${count} Titeln`
    case 'index-serialize': return `Suchdaten vorbereiten: ${count} Titeln`
    case 'index-signature': return 'Bibliotheksstände werden verglichen …'
    case 'index-reset': return 'Alter Suchindex wird ersetzt …'
    case 'index-playlists': return `Playlists speichern: ${count}`
    case 'saving': return 'Bibliotheksstand wird gespeichert …'
    case 'done': return `${total} Titel geladen`
    case 'failed': return 'Aktualisierung fehlgeschlagen. Der gespeicherte Stand bleibt erhalten.'
    default: return 'Bibliothek wird aktualisiert …'
  }
}

function duration(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds))
  return value >= 60 ? `${Math.floor(value / 60)} min ${value % 60} s` : `${value} s`
}

export function ImportProgress({ status }: { status: Status }) {
  // Anchor only to a received status, so the local timer continues while a
  // request is pending and never counts a UI rerender as actual progress.
  const receivedAt = useMemo(() => performance.now(), [status])
  const [now, setNow] = useState(() => performance.now())
  useEffect(() => {
    if (!status.refreshing) return
    const timer = window.setInterval(() => setNow(performance.now()), 1000)
    return () => window.clearInterval(timer)
  }, [status.refreshing])

  const progress = status.progress
  if (!progress && !status.refreshing) return null
  const activePhase = progress && !['done', 'failed'].includes(progress.stage)
  const message = !progress || (status.refreshing && !activePhase)
    ? 'Bibliotheksabgleich wird gestartet …'
    : !status.refreshing && activePhase
      ? status.error?.message ?? 'Bibliotheksabgleich beendet.'
      : progressMessage(progress)
  const delta = status.refreshing ? Math.max(0, (now - receivedAt) / 1000) : 0
  const hasTiming = progress && [progress.elapsedSeconds, progress.stageElapsedSeconds, progress.idleSeconds].every(Number.isFinite)
  const idle = hasTiming ? progress.idleSeconds + delta : 0
  const failed = !status.refreshing && (progress?.stage === 'failed' || Boolean(status.error))
  const counted = status.refreshing && activePhase && countedStages.has(progress.stage) && progress.total > 0
  const hint = status.refreshing
    ? `Bibliothek wird im Hintergrund aktualisiert. ${status.hasCache ? 'Du kannst den gespeicherten Stand weiter durchsuchen.' : 'Deine Titel erscheinen nach dem ersten Import.'}`
    : failed ? (status.hasCache ? 'Der gespeicherte Bibliotheksstand bleibt nutzbar.' : 'Der erste Import wurde nicht abgeschlossen.') : 'Letzter abgeschlossener Bibliotheksabgleich.'

  return <section className={`import-progress ${failed ? 'is-failed' : status.refreshing ? 'is-active' : 'is-complete'}`}
    aria-label="Bibliotheksfortschritt">
    <div className="import-progress-header">
      {status.refreshing ? <LoaderCircle size={18} className="spin" aria-hidden="true" /> : failed ? <X size={18} aria-hidden="true" /> : <CheckCheck size={18} aria-hidden="true" />}
      <div><p className="import-progress-phase" aria-live="polite" aria-atomic="true">{message}</p><p className="import-progress-hint">{hint}</p></div>
    </div>
    {counted && <progress className="import-progress-bar" max={progress.total} value={Math.min(progress.total, Math.max(0, progress.completed))}
      aria-label="Fortschritt dieses Arbeitsschritts" aria-valuetext={`${number.format(progress.completed)} von ${number.format(progress.total)}`} />}
    {hasTiming && <dl className="import-progress-times" aria-live="off">
      <div><dt>Gesamt</dt><dd>{duration(progress.elapsedSeconds + delta)}</dd></div>
      <div><dt>Schritt</dt><dd>{duration(progress.stageElapsedSeconds + delta)}</dd></div>
      {status.refreshing && <div><dt>Letzte Fortschrittsmeldung vor</dt><dd>{duration(idle)}</dd></div>}
    </dl>}
    {status.refreshing && (idle >= 30 || delta >= 10) && <p className="import-progress-diagnostic">
      {delta >= 10 ? `Status seit ${duration(delta)} nicht aktualisiert. ` : ''}
      {idle >= 30 ? 'Seit mindestens 30 s keine neue Fortschrittsmeldung. ' : ''}
      Details findest du in der Mac-App unter „Diagnoseprotokolle öffnen“.
    </p>}
  </section>
}
