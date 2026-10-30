import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  ArrowDownUp, ArrowLeft, ArrowRight, Check, CheckCheck, ChevronDown, Cloud,
  Copy, Disc3, Ellipsis, Headphones, Library, ListMusic, LoaderCircle, Menu,
  Monitor, Music2, Plug, RefreshCw, Search, Settings2, ShieldCheck, Star, Trash2, X,
} from 'lucide-react'
import { api, ApiError, initializeSession, loginSession, logoutSession } from './api'
import { ImportProgress } from './ImportProgress'
import { LoginScreen } from './LoginScreen'
import { useRatingQueue } from './useRatingQueue'
import type { Device, DeviceTokens, PermissionResult, Playlist, Status, Track, TrackPage } from './api'

function formatDuration(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
const dateFormatter = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
function AddedDate({ value }: { value: string | null }) {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return <span title="Hinzufügedatum nicht verfügbar">—</span>
  return <time dateTime={value ?? undefined} title={date.toLocaleString('de-DE')}>{dateFormatter.format(date)}</time>
}
function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Die Anfrage konnte nicht ausgeführt werden.'
}
function Cover({ track, large = false, enabled = true }: { track: Track; large?: boolean; enabled?: boolean }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => { if (enabled) setFailed(false) }, [enabled, track.id])
  const seed = [...track.album].reduce((sum, c) => sum + c.charCodeAt(0), 0) % 6
  return <div className={`cover cover-${seed} ${large ? 'cover-large' : ''}`} aria-hidden="true">
    {enabled && track.hasArtwork && !failed
      ? <img src={`/api/v1/tracks/${track.id}/artwork`} alt="" onError={() => setFailed(true)} loading="lazy" />
      : <><span className="cover-shape" /><span className="cover-disc" /><span className="cover-label">{track.album.slice(0, 2).toUpperCase()}</span></>}
  </div>
}
function Stars({ track, busy, onRate, disabled = false }: {
  track: Track; busy: boolean; onRate: (track: Track, stars: number) => void; disabled?: boolean
}) {
  const [hover, setHover] = useState(0)
  const value = hover || track.ratingRaw / 20
  return <div className={`stars ${track.ratingOrigin === 'album' && !hover ? 'inherited' : ''}`} onMouseLeave={() => setHover(0)}
    role="group" aria-label={`Bewertung für ${track.title}${track.ratingOrigin === 'album' ? ', vom Album übernommen' : ''}`}>
    {[1, 2, 3, 4, 5].map(i => <button key={i} className={`star-button ${value >= i ? 'on' : value >= i - .5 ? 'half' : ''}`}
      type="button" aria-label={`${i} ${i === 1 ? 'Stern' : 'Sterne'} für ${track.title}`}
      aria-pressed={track.ratingOrigin === 'user' && track.ratingRaw === i * 20}
      disabled={disabled || track.ratingCapability === 'unavailable'}
      onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} onBlur={() => setHover(0)} onClick={() => { setHover(0); onRate(track, i) }}>
      <Star size={17} strokeWidth={1.5} />
    </button>)}
    {busy && <LoaderCircle className="spin rating-spinner" size={13} aria-label="Wird gespeichert" />}
  </div>
}
function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { ref.current?.showModal() }, [])
  return <dialog ref={ref} className="modal" aria-label={title} onCancel={e => { e.preventDefault(); onClose() }}
    onClick={e => { if (e.target === ref.current) onClose() }}>
    <div className="modal-header"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Schließen"><X size={20} /></button></div>
    {children}
  </dialog>
}
function ConnectionSettings({ onClose, onUpdated, onLogout }: { onClose: () => void; onUpdated: () => Promise<void>; onLogout: () => Promise<void> }) {
  const [devices, setDevices] = useState<Device[]>([])
  const [name, setName] = useState('iPad-Testclient')
  const [tokens, setTokens] = useState<DeviceTokens | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState('')
  const [requestingPermissions, setRequestingPermissions] = useState(false)
  const [permissions, setPermissions] = useState<PermissionResult | null>(null)
  const load = useCallback(() => api<{ items: Device[] }>('auth/devices').then(d => setDevices(d.items)).catch(e => setError(errorMessage(e))), [])
  useEffect(() => { void load() }, [load])
  async function create() {
    setBusy(true); setError(''); setTokens(null)
    try { setTokens(await api<DeviceTokens>('auth/devices', 'POST', { name })); await load() }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  async function revoke(id: string) {
    try { await api(`auth/devices/${id}`, 'DELETE'); if (tokens?.deviceId === id) setTokens(null); await load() }
    catch (e) { setError(errorMessage(e)) }
  }
  async function copy(value: string, key: string) {
    try { await navigator.clipboard.writeText(value); setCopied(key) }
    catch { setError('Kopieren ist in diesem Browser nicht verfügbar. Bitte markiere den Schlüssel manuell.') }
  }
  async function requestPermissions() {
    setRequestingPermissions(true); setError(''); setPermissions(null)
    try { setPermissions(await api<PermissionResult>('permissions/request', 'POST')); await onUpdated() }
    catch (e) { setError(errorMessage(e)) } finally { setRequestingPermissions(false) }
  }
  return <Modal title="Verbindung & API" onClose={onClose}>
    <div className="connection-card"><Monitor size={23} /><div><strong>Zugriff im lokalen Netzwerk</strong><p>Öffne die Netzwerkadresse der Mac-App auf dem anderen Gerät und melde dich mit dem Webpasswort an. Das Passwort bleibt bei App-Updates gleich. Beide Geräte müssen im selben Netzwerk sein.</p></div></div>
    <button className="button" onClick={() => void onLogout().catch(failure => setError(errorMessage(failure)))}>Abmelden</button>
    <a className="text-link" href="/api/v1/openapi.json" target="_blank" rel="noreferrer">OpenAPI-Vertrag ansehen <ArrowRight size={14} /></a>
    <h3>Berechtigungen</h3>
    <p className="muted">Bibliothekszugriff und Automation werden getrennt angefragt. Musik wird zur Prüfung gegebenenfalls geöffnet. Es werden keine Bewertungen geändert.</p>
    <button className="button" disabled={requestingPermissions} onClick={() => void requestPermissions()}>{requestingPermissions ? <LoaderCircle size={16} className="spin" /> : <ShieldCheck size={16} />} {requestingPermissions ? 'Bitte macOS-Dialoge beantworten …' : 'Berechtigungen anfordern'}</button>
    {permissions && <div role="status" className="muted"><p>{permissions.media.message}</p>{permissions.mode !== 'demo' && <p>{permissions.automation.message}</p>}{permissions.needsSettings && <p>Nach einer Ablehnung öffne in der Mac-App die Datenschutzeinstellungen für Medien & Apple Music oder Automation.</p>}{permissions.libraryError && <p className="inline-error">{permissions.libraryError.message}</p>}</div>}
    <h3>Lokaler Gerätezugang</h3><p className="muted">Für die Entwicklung eines nativen Clients. Zugangsdaten werden nur einmal angezeigt.</p>
    <form className="device-form" onSubmit={e => { e.preventDefault(); void create() }}>
      <label className="sr-only" htmlFor="device-name">Gerätename</label><input id="device-name" value={name} maxLength={80} onChange={e => setName(e.target.value)} required />
      <button className="button button-primary" disabled={busy || !name.trim()}>{busy ? <LoaderCircle size={16} className="spin" /> : <Plug size={16} />} Zugang erstellen</button>
    </form>
    {tokens && <div className="token-panel">
      <p><CheckCheck size={16} /> Zugang erstellt. Bewahre beide Schlüssel sicher auf.</p>
      {([['Zugriffstoken · 1 Stunde', tokens.accessToken, 'access'], ['Erneuerungstoken · 30 Tage', tokens.refreshToken, 'refresh']] as const).map(([label, token, key]) =>
        <div key={key}><label htmlFor={`token-${key}`}>{label}</label><div className="token-row"><input id={`token-${key}`} type="password" value={token} readOnly autoComplete="off" /><button className="icon-button" aria-label={`${label} kopieren`} onClick={() => void copy(token, key)}>{copied === key ? <Check size={17} /> : <Copy size={17} />}</button></div></div>)}
    </div>}
    {devices.length > 0 && <ul className="device-list">{devices.map(device => <li key={device.id}><span><Monitor size={16} />{device.name}</span><button className="icon-button danger" aria-label={`Zugang für ${device.name} widerrufen`} onClick={() => void revoke(device.id)}><Trash2 size={16} /></button></li>)}</ul>}
    {error && <p role="alert" className="inline-error">{error}</p>}
  </Modal>
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(false)
  const [checkingSession, setCheckingSession] = useState(true)
  const [authError, setAuthError] = useState('')
  const [status, setStatus] = useState<Status | null>(null)
  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [page, setPage] = useState<TrackPage | null>(null)
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [rating, setRating] = useState('all')
  const [playlistId, setPlaylistId] = useState('')
  const [sort, setSort] = useState('artist')
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [selectedTrack, setSelected] = useState<Track | null>(null)
  const [settings, setSettings] = useState(false)
  const [navOpen, setNavOpen] = useState(false)
  const [cursors, setCursors] = useState<string[]>([''])
  const [pageIndex, setPageIndex] = useState(0)
  const pageRef = useRef(page)
  const pendingRef = useRef(false)
  const requests = useRef(0)
  const queuePanel = useRef<HTMLDivElement>(null)
  const pageSize = 50
  pageRef.current = page

  const report = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.code === 'UNAUTHORIZED') { setAuthenticated(false); setAuthError(e.message) }
    setError(errorMessage(e))
  }, [])

  const loadStatus = useCallback(async () => {
    const [next, lists] = await Promise.all([api<Status>('status'), api<{ items: Playlist[] }>('playlists')])
    setStatus(next); setPlaylists(lists.items.filter(p => !p.isMaster))
    if (next.error) setError(next.error.message)
    return next
  }, [])

  const updateTrack = useCallback((next: Track, scope: string) => {
    setPage(previous => previous?.libraryScope === scope
      ? { ...previous, items: previous.items.map(track => track.id === next.id ? next : track) } : previous)
    setSelected(previous => pageRef.current?.libraryScope === scope && previous?.id === next.id ? next : previous)
  }, [])
  const queue = useRatingQueue(authenticated ? status : null, {
    onConfirmed: job => {
      if (!job.result || !('track' in job.result)) return
      updateTrack(job.result.track, job.libraryScope)
      setNotice(job.stars ? `„${job.title}“ mit ${job.stars} ${job.stars === 1 ? 'Stern' : 'Sternen'} gespeichert` : 'Eigene Bewertung entfernt')
    },
    onError: (failure, scope) => {
      if (failure instanceof ApiError && failure.details.track) updateTrack(failure.details.track as Track, scope)
      report(failure)
    },
    onUpdated: () => { void loadStatus().catch(report) },
    onRecovered: message => { setError(previous => previous === message ? '' : previous) },
  })
  const pendingStars = queue.pendingStars
  pendingRef.current = queue.pendingCount > 0

  const loadTracks = useCallback(async (cursor = '', append = false) => {
    const current = ++requests.current
    setLoading(true)
    const params = new URLSearchParams({ query: search, rating, playlistId, sort, limit: String(pageSize), cursor })
    try {
      const next = await api<TrackPage>(`tracks?${params}`)
      if (current === requests.current) {
        setPage(next)
        if (!append && !cursor) { setCursors(['']); setPageIndex(0) }
      }
    } catch (e) {
      if (current !== requests.current) return
      if (e instanceof ApiError && e.code === 'CURSOR_EXPIRED') {
        setCursors(['']); setPageIndex(0)
        params.set('cursor', '')
        try {
          const next = await api<TrackPage>(`tracks?${params}`)
          if (current === requests.current) setPage(next)
        } catch (retryError) { report(retryError) }
      } else report(e)
    } finally { if (current === requests.current) setLoading(false) }
  }, [search, rating, playlistId, sort, report])

  useEffect(() => {
    let alive = true
    initializeSession().then(async () => {
      if (!alive) return
      await loadStatus()
      if (alive) setAuthenticated(true)
    }).catch(e => {
      if (alive && !(e instanceof ApiError && e.code === 'UNAUTHORIZED')) setAuthError(errorMessage(e))
    }).finally(() => { if (alive) setCheckingSession(false) })
    return () => { alive = false }
  }, [loadStatus])
  useEffect(() => { const timer = window.setTimeout(() => setSearch(query), 220); return () => window.clearTimeout(timer) }, [query])
  useEffect(() => { if (authenticated) void loadTracks() }, [authenticated, loadTracks])
  useEffect(() => {
    if (!authenticated) return
    let alive = true
    let active = false
    async function poll() {
      if (document.hidden || active || pendingRef.current || connecting || refreshing) return
      active = true
      try {
        // Poll the shared cache; a native import starts on connect or manual refresh.
        const next = await api<Status>('status')
        if (!alive) return
        if (next.error) setError(next.error.message)
        if (next.snapshotRevision !== pageRef.current?.snapshotRevision || (status?.refreshing && !next.refreshing)) {
          await loadTracks()
          const lists = await api<{ items: Playlist[] }>('playlists')
          if (alive) setPlaylists(lists.items.filter(p => !p.isMaster))
        }
        // Changing refreshing restarts this effect; finish dependent updates before its cleanup.
        if (alive) setStatus(next)
      } catch (e) { if (alive) report(e) } finally { active = false }
    }
    const timer = window.setInterval(() => void poll(), status?.refreshing ? 1000 : 30_000)
    const wake = () => { if (!document.hidden) void poll() }
    document.addEventListener('visibilitychange', wake)
    return () => { alive = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', wake) }
  }, [authenticated, connecting, refreshing, status?.refreshing, loadTracks, report])

  async function connect(mode: 'music' | 'demo') {
    if (pendingRef.current) return
    setConnecting(true); setError(''); setNotice('')
    try {
      const next = await api<Status>('library/connect', 'POST', { mode, background: true })
      setStatus(next)
      setQuery(''); setSearch(''); setRating('all'); setPlaylistId('')
      await loadStatus()
      ++requests.current
      const first = await api<TrackPage>(`tracks?sort=${sort}&limit=${pageSize}`)
      setPage(first); setCursors(['']); setPageIndex(0); setLoading(false)
    } catch (e) { report(e); await loadStatus().catch(() => {}) }
    finally { setConnecting(false) }
  }
  async function refresh() {
    setRefreshing(true); setError('')
    try { setStatus(await api<Status>('library/refresh', 'POST', { background: true })) }
    catch (e) { report(e) } finally { setRefreshing(false) }
  }
  function rate(track: Track, stars: number) {
    if (!pageRef.current?.libraryScope || !status?.connected || status.refreshing || connecting) return
    setError(''); setNotice('')
    queue.enqueue(track, stars)
  }
  function navigate(nextRating: string, playlist = '') {
    setRating(nextRating); setPlaylistId(playlist); setQuery(''); setNavOpen(false)
  }
  function changePage(direction: 1 | -1) {
    if (direction === 1 && page?.nextCursor) {
      const next = [...cursors.slice(0, pageIndex + 1), page.nextCursor]
      setCursors(next); setPageIndex(pageIndex + 1); void loadTracks(page.nextCursor, true)
    } else if (direction === -1 && pageIndex > 0) {
      setPageIndex(pageIndex - 1); void loadTracks(cursors[pageIndex - 1], true)
    }
  }

  function displayRating(track: Track): Track {
    const stars = pendingStars.get(track.id)
    // Keep confirmed data and revisions intact while showing the pending choice.
    return stars === undefined ? track : { ...track, ratingRaw: stars * 20, ratingOrigin: stars ? 'user' : 'none' }
  }
  const selected = selectedTrack ? displayRating(selectedTrack) : null
  const title = playlists.find(p => p.id === playlistId)?.name ?? (rating === 'unrated' ? 'Noch zu entdecken.' : rating === 'rated' ? 'Deine Favoriten.' : 'Deine Sammlung.')
  const counts = status?.counts ?? { total: 0, rated: 0, unrated: 0 }
  const hasLibrary = Boolean(status?.hasCache)
  const importing = Boolean(status?.refreshing)
  const canRate = Boolean(status?.connected) && !connecting && !importing
  const heroes = page?.items.filter((t, i, list) => list.findIndex(other => other.album === t.album) === i).slice(0, 2) ?? []

  if (!authenticated) return <LoginScreen checking={checkingSession} message={authError} onLogin={async password => {
    await loginSession(password)
    await loadStatus()
    setAuthError(''); setError(''); setAuthenticated(true)
  }} />

  return <div className="app-shell">
    {navOpen && <button className="nav-scrim" aria-label="Navigation schließen" onClick={() => setNavOpen(false)} />}
    <aside className={`sidebar ${navOpen ? 'open' : ''}`} aria-label="Hauptnavigation">
      <a className="brand" href="/" onClick={e => { e.preventDefault(); navigate('all') }}><span className="brand-mark"><Music2 size={22} strokeWidth={1.8} /></span><span>iTunes<span className="brand-light">Remote</span><small>DEINE MUSIK. DEINE STERNE.</small></span></a>
      <div className="sidebar-section">BIBLIOTHEK</div>
      <nav>
        <button className={`nav-item ${rating === 'all' && !playlistId ? 'active' : ''}`} onClick={() => navigate('all')}><Library size={18} /><span>Alle Titel</span><span className="nav-count">{counts.total.toLocaleString('de')}</span></button>
        <button className={`nav-item ${rating === 'unrated' && !playlistId ? 'active' : ''}`} onClick={() => navigate('unrated')}><Disc3 size={18} /><span>Unbewertet</span><span className="nav-count">{counts.unrated.toLocaleString('de')}</span></button>
        <button className={`nav-item ${rating === 'rated' && !playlistId ? 'active' : ''}`} onClick={() => navigate('rated')}><Star size={18} /><span>Bewertet</span><span className="nav-count">{counts.rated.toLocaleString('de')}</span></button>
      </nav>
      <div className="sidebar-section playlist-heading"><span>PLAYLISTS</span><ListMusic size={14} /></div>
      <nav className="playlist-nav">{playlists.length ? playlists.map(playlist => <button key={playlist.id} className={`nav-item ${playlistId === playlist.id ? 'active' : ''}`} onClick={() => navigate('all', playlist.id)}><ListMusic size={17} /><span>{playlist.name}</span><span className="nav-count">{playlist.trackCount}</span></button>) : <p className="sidebar-empty">Deine Playlists erscheinen nach dem Verbinden.</p>}</nav>
      <div className="sidebar-bottom"><div className="local-note"><ShieldCheck size={18} /><div><strong>Deine Musik bleibt bei dir.</strong><span>Direkt von deinem Mac.</span></div></div><button className="nav-item" onClick={() => setSettings(true)}><Settings2 size={17} /><span>Verbindung & API</span></button><div className="version">iTunesRemote <span>0.1</span></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" onClick={() => setNavOpen(true)} aria-label="Navigation öffnen"><Menu size={22} /></button><Headphones size={17} /><span>Bibliothek</span><span className="breadcrumb-separator">/</span><strong>{playlistId ? 'Playlist' : rating === 'unrated' ? 'Unbewertet' : rating === 'rated' ? 'Bewertet' : 'Alle Titel'}</strong></div><div className="topbar-right"><span className="connection-status"><span className={`status-dot ${status?.connected ? 'connected' : ''}`} />{status?.connected ? 'Mit Mac verbunden' : 'Lokaler Mac'}</span><button className="icon-button" onClick={() => void refresh()} disabled={!hasLibrary || refreshing || connecting || importing} aria-label="Bibliothek aktualisieren" title="Bibliothek aktualisieren"><RefreshCw size={17} className={refreshing ? 'spin' : ''} /></button></div></header>
      {status?.mode === 'demo' && <div className="demo-banner"><span><Disc3 size={15} /><strong>Demobibliothek</strong><span className="demo-explanation">Nur Beispieldaten werden geändert.</span></span><button disabled={connecting || importing || pendingStars.size > 0} onClick={() => void connect('music')}>Eigene Bibliothek verbinden <ArrowRight size={14} /></button></div>}
      <main>
        <section className="hero"><div><p className="eyebrow">DEIN PERSÖNLICHES MUSIKARCHIV</p><h1>{hasLibrary ? title : <>Gute Musik.<br /><em>Dein Geschmack.</em></>}</h1><p className="hero-description">{hasLibrary ? (rating === 'unrated' ? 'Gib den nächsten Lieblingsstücken ihre Sterne.' : 'Entdecke deine Bibliothek neu. Ein Titel, eine Bewertung, dein Gefühl.') : 'Deine Musikbibliothek durchstöbern. Lieblingsstücke entdecken. Sterne vergeben.'}</p>{hasLibrary && <div className="collection-stats"><span><Music2 size={15} /><strong>{counts.total.toLocaleString('de')}</strong> Titel</span><span className="stat-divider" /><span><Star size={15} /><strong>{counts.unrated.toLocaleString('de')}</strong> ohne eigene Bewertung</span></div>}</div><div className="hero-records" aria-hidden="true">{heroes.length > 0 ? heroes.map((t, i) => <div key={t.id} className={`hero-cover hero-cover-${i}`}><Cover track={t} large enabled={!importing} /></div>) : <><div className="hero-cover hero-cover-0"><div className="cover cover-3 cover-large"><span className="cover-shape" /><span className="cover-disc" /><span className="cover-label">YOUR<br />MUSIC</span></div></div><div className="hero-cover hero-cover-1"><div className="cover cover-1 cover-large"><span className="cover-shape" /><span className="cover-disc" /></div></div></>}</div></section>

        {error && <div className="error-banner" role="alert"><span>{error}</span><button className="icon-button" aria-label="Fehlermeldung schließen" onClick={() => setError('')}><X size={17} /></button></div>}
        {(queue.pendingCount > 0 || queue.failedCount > 0) && <div ref={queuePanel} className="cache-banner rating-queue" role="region" aria-label="Bewertungswarteschlange">
          <div>{queue.pendingCount > 0 && <p><LoaderCircle className="spin" size={15} /> {queue.pendingCount} {queue.pendingCount === 1 ? 'Bewertung ausstehend' : 'Bewertungen ausstehend'} · {queue.uploadingCount ? 'Wird an den Mac übertragen …' : 'Wird im Hintergrund gespeichert …'}</p>}
            {queue.failedCount > 0 && <><p>{queue.failedCount} {queue.failedCount === 1 ? 'Bewertung nicht gespeichert' : 'Bewertungen nicht gespeichert'}. Bitte wähle die Sterne erneut.</p><p>Nicht gespeichert: {queue.failedTitles.join(' · ')}</p></>}
          </div>
          {queue.failedCount > 0 && <button className="button" onClick={() => void queue.dismissErrors()}>Fehler verwerfen</button>}
        </div>}
        {status && !authError && <ImportProgress status={status} />}
        {hasLibrary && !status?.connected && !importing && !authError && <div className="cache-banner"><span>Gespeicherter Bibliotheksstand. Verbinde die Bibliothek, um Bewertungen zu speichern.</span><button className="button" disabled={connecting} onClick={() => void connect(status?.mode ?? 'music')}>{connecting ? <LoaderCircle size={14} className="spin" /> : <Plug size={14} />} {connecting ? 'Bibliothek wird eingelesen …' : 'Verbinden'}</button></div>}

        {!hasLibrary ? <section className="welcome-panel"><div className="welcome-icon"><Library size={28} /></div><h2>Deine Sammlung wartet.</h2><p>Verbinde die Musikbibliothek dieses Macs.<br />Bewertungen werden direkt in der Musik-App gespeichert.</p><div className="welcome-actions"><button className="button button-primary" disabled={connecting || importing} onClick={() => void connect('music')}>{connecting || importing ? <LoaderCircle size={17} className="spin" /> : <Plug size={17} />} {connecting || importing ? 'Bibliothek wird eingelesen …' : 'Bibliothek verbinden'}</button><button className="button button-quiet" disabled={connecting || importing} onClick={() => void connect('demo')}>Demo ausprobieren <ArrowRight size={16} /></button></div><p className="welcome-footnote"><ShieldCheck size={14} /> macOS fragt nach deiner Freigabe. Deine Daten bleiben auf deinem Mac.</p></section>
        : <section className="library-section" aria-label="Titelübersicht">
          <div className="toolbar"><label className="search-field"><Search size={19} /><span className="sr-only">Bibliothek durchsuchen</span><input value={query} maxLength={300} onChange={e => setQuery(e.target.value)} placeholder="Titel, Interpret oder Album suchen …" />{query && <button className="icon-button" aria-label="Suche leeren" onClick={() => setQuery('')}><X size={15} /></button>}</label><div className="toolbar-filters"><label className="select-field"><ArrowDownUp size={16} /><span className="sr-only">Sortierung</span><select value={sort} onChange={e => setSort(e.target.value)}><option value="artist">Interpret</option><option value="title">Titel</option><option value="album">Album</option><option value="rating">Bewertung</option><option value="duration">Dauer</option><option value="addedDate">Hinzugefügt: neueste zuerst</option><option value="addedDateAsc">Hinzugefügt: älteste zuerst</option></select><ChevronDown size={13} /></label><label className="select-field"><Star size={16} /><span className="sr-only">Bewertungsfilter</span><select value={rating} onChange={e => setRating(e.target.value)}><option value="all">Alle Bewertungen</option><option value="unrated">Ohne eigene Bewertung</option><option value="rated">Mit eigener Bewertung</option>{[1, 2, 3, 4, 5].map(i => <option value={String(i)} key={i}>{i} {i === 1 ? 'Stern' : 'Sterne'}</option>)}</select><ChevronDown size={13} /></label></div></div>
          <div className="list-meta"><span>{loading ? 'Wird geladen …' : `${(page?.total ?? 0).toLocaleString('de')} ${(page?.total ?? 0) === 1 ? 'Titel' : 'Titel'}`}{search && <> für „{search}“</>}</span><span><Star size={12} /> Ein Klick. Deine Bewertung.</span></div>
          <div className={`track-list ${loading ? 'is-loading' : ''}`} aria-busy={loading}>
            <div className="table-head"><span>TITEL</span><span>INTERPRET</span><span>ALBUM</span><span className="duration-cell">DAUER</span><span className="added-cell">HINZUGEFÜGT</span><span>BEWERTUNG</span><span /></div>
            {page?.items.map(track => <div className="track-row" key={track.id}>
              <button className="track-main" onClick={() => setSelected(track)}><Cover track={track} enabled={!importing} /><span><strong>{track.title}</strong><small>{track.artist || 'Unbekannter Interpret'}</small><small className="track-added">Hinzugefügt <AddedDate value={track.addedDate} /></small></span>{track.isCloud && <Cloud size={14} className="cloud-mark" aria-label="Cloudtitel" />}</button>
              <span className="artist-cell">{track.artist || '—'}</span><span className="album-cell">{track.album || '—'}</span><span className="duration-cell">{formatDuration(track.durationSeconds)}</span>
              <span className="added-cell"><AddedDate value={track.addedDate} /></span>
              <div className="rating-cell"><Stars track={displayRating(track)} busy={pendingStars.has(track.id)} onRate={(t, value) => void rate(t, value)} disabled={!canRate} />{displayRating(track).ratingOrigin === 'album' && <span className="inherited-label">Vom Album</span>}</div>
              <button className="icon-button row-more" onClick={() => setSelected(track)} aria-label={`Details zu ${track.title}`}><Ellipsis size={18} /></button>
            </div>)}
            {!loading && !page?.items.length && <div className="empty-state"><Search size={28} /><h3>Hier ist es gerade still.</h3><p>Für diese Auswahl wurden keine Titel gefunden.</p><button className="button" onClick={() => { setQuery(''); setRating('all'); setPlaylistId('') }}>Filter zurücksetzen</button></div>}
          </div>
          <footer className="list-footer"><span>{page?.total ? `${pageIndex * pageSize + 1}–${pageIndex * pageSize + (page?.items.length ?? 0)} von ${page.total.toLocaleString('de')}` : 'Keine Titel'}<span className="footer-sync">{status?.lastSyncedAt && ` · Stand ${new Date(status.lastSyncedAt).toLocaleTimeString('de', { hour: '2-digit', minute: '2-digit' })}`}</span></span><div className="pagination"><button className="icon-button" aria-label="Vorherige Seite" disabled={pageIndex === 0 || loading} onClick={() => changePage(-1)}><ArrowLeft size={17} /></button><span>{pageIndex + 1}</span><button className="icon-button" aria-label="Nächste Seite" disabled={!page?.nextCursor || loading} onClick={() => changePage(1)}><ArrowRight size={17} /></button></div></footer>
        </section>}
        <div className="page-footnote"><span>Mit Liebe zur eigenen Sammlung.</span><span><Monitor size={13} /> Läuft auf deinem Mac</span></div>
      </main>
    </div>
    <div className={`save-notice ${notice || queue.pendingCount || queue.failedCount ? 'visible' : ''}`} role="status" aria-live="polite">
      {queue.pendingCount > 0 ? <><LoaderCircle className="spin" size={17} /><span>{queue.pendingCount} {queue.pendingCount === 1 ? 'Bewertung vorgemerkt' : 'Bewertungen vorgemerkt'}. Speicherung im Hintergrund.</span></>
        : queue.failedCount > 0 ? <><X size={17} /><span>{queue.failedCount} {queue.failedCount === 1 ? 'Bewertung nicht gespeichert' : 'Bewertungen nicht gespeichert'}.</span><button className="button button-quiet" onClick={() => queuePanel.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })}>Ansehen</button></>
          : notice && <><CheckCheck size={17} /><span>{notice}</span><button className="icon-button" aria-label="Bestätigung schließen" onClick={() => setNotice('')}><X size={14} /></button></>}
    </div>
    {selected && <Modal title="Titeldetails" onClose={() => setSelected(null)}><div className="detail-heading"><Cover track={selected} large enabled={!importing} /><div><p className="eyebrow">{selected.genre || 'DEINE BIBLIOTHEK'}</p><h3>{selected.title}</h3><p>{selected.artist}</p><p className="muted">{selected.album}</p></div></div><dl className="detail-grid"><div><dt>Jahr</dt><dd>{selected.year ?? '—'}</dd></div><div><dt>Dauer</dt><dd>{formatDuration(selected.durationSeconds)}</dd></div><div><dt>Hinzugefügt</dt><dd><AddedDate value={selected.addedDate} /></dd></div><div><dt>Gespielt</dt><dd>{selected.playCount} Mal</dd></div><div><dt>Verfügbarkeit</dt><dd>{selected.isCloud ? 'Cloudtitel' : 'Bibliothek'}</dd></div></dl><div className="detail-rating"><div><h3>Deine Bewertung</h3><p className="muted">{selected.ratingOrigin === 'album' ? 'Diese Sterne sind vom Album übernommen.' : selected.ratingOrigin === 'user' ? `${selected.ratingRaw / 20} von 5 Sternen · selbst vergeben` : 'Noch keine eigene Bewertung.'}</p></div><Stars track={selected} busy={pendingStars.has(selected.id)} onRate={(t, value) => void rate(t, value)} disabled={!canRate} /></div>{selected.capabilityReason && <p role="alert" className="inline-error">{selected.capabilityReason}</p>}{selected.ratingOrigin === 'user' && <button className="button button-quiet" disabled={!canRate} onClick={() => void rate(selected, 0)}><X size={15} /> Eigene Bewertung entfernen</button>}<p className="detail-footnote"><ShieldCheck size={14} /> {status?.mode === 'demo' ? 'Änderungen bleiben in der Demobibliothek.' : 'Bewertungen werden in der Musik-App gespeichert.'}</p></Modal>}
    {settings && <ConnectionSettings onClose={() => setSettings(false)} onUpdated={async () => { await loadStatus(); await loadTracks() }} onLogout={async () => {
      await logoutSession()
      ++requests.current
      setSettings(false); setSelected(null); setAuthenticated(false); setAuthError(''); setError('')
      setPage(null); setStatus(null); setPlaylists([]); setNotice('')
    }} />}
  </div>
}
