import { useState } from 'react'
import { LoaderCircle, Music2, ShieldCheck } from 'lucide-react'

export function LoginScreen({ checking, message, onLogin }: {
  checking: boolean; message: string; onLogin: (password: string) => Promise<void>
}) {
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    setBusy(true); setError('')
    try { await onLogin(password); setPassword('') }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Die Anmeldung ist fehlgeschlagen.') }
    finally { setBusy(false) }
  }

  return <main className="login-screen">
    <section className="login-card" aria-labelledby="login-title">
      <div className="login-brand"><span className="brand-mark"><Music2 size={25} /></span><strong>iTunesRemote</strong></div>
      <h1 id="login-title">Mit deinem Mac verbinden</h1>
      <p>Melde dich mit dem Passwort aus der iTunesRemote-App an.</p>
      <form onSubmit={event => { event.preventDefault(); void submit() }}>
        <label htmlFor="web-password">Passwort</label>
        <input id="web-password" name="password" type={visible ? 'text' : 'password'} autoComplete="current-password"
          value={password} onChange={event => setPassword(event.target.value)} required maxLength={128}
          disabled={checking || busy} aria-describedby="password-help" />
        <label className="login-show-password"><input type="checkbox" checked={visible} onChange={event => setVisible(event.target.checked)} />Passwort anzeigen</label>
        {(error || message) && <p role="alert" className="inline-error">{error || message}</p>}
        <button className="button button-primary" disabled={checking || busy || !password}>
          {(checking || busy) && <LoaderCircle size={17} className="spin" />}
          {checking ? 'Sitzung wird geprüft …' : busy ? 'Anmeldung läuft …' : 'Anmelden'}
        </button>
      </form>
      <p id="password-help" className="login-help"><ShieldCheck size={17} /><span>In der Mac-App unter „Webpasswort“ anzeigen oder kopieren. Das Passwort bleibt bei App-Updates gleich.</span></p>
    </section>
  </main>
}
