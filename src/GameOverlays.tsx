import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { ChevronRight, Moon, Music2, Pause, RefreshCw, Settings, ShieldAlert, Sun, Vibrate, Volume2, X } from 'lucide-react'
import { useSensoryPreferences } from './sensoryPreferences'
import { useDialogFocus } from './useDialogFocus'
import './menu.css'

type Theme = 'light' | 'dark' | 'system'

function useGameTheme(theme: Theme) {
  useEffect(() => {
    localStorage.setItem('motman-theme', theme)
    const systemTheme = matchMedia('(prefers-color-scheme: dark)')
    const applyTheme = () => {
      document.documentElement.dataset.theme = theme === 'system'
        ? (systemTheme.matches ? 'dark' : 'light')
        : theme
    }
    applyTheme()
    if (theme !== 'system') return
    systemTheme.addEventListener('change', applyTheme)
    return () => systemTheme.removeEventListener('change', applyTheme)
  }, [theme])
}

function Toggle({ icon, label, checked, setChecked }: {
  icon: ReactNode
  label: string
  checked: boolean
  setChecked: (value: boolean) => void
}) {
  return <label className="mm-setting-row"><span>{icon}{label}</span><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} /><i /></label>
}

export function GameOptionsOverlay({ close, newGrid, report }: { close: () => void; newGrid?: () => void; report?: () => void }) {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('motman-theme') as Theme | null) ?? 'light')
  const { preferences, setPreference } = useSensoryPreferences()
  const dialogRef = useDialogFocus<HTMLElement>(close)
  useGameTheme(theme)

  return <div className="mm-modal-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && close()}>
    <section ref={dialogRef} className="mm-settings mm-game-options" role="dialog" aria-modal="true" aria-label="Paramètres de la partie" tabIndex={-1}>
      <header><h2>Paramètres</h2><button type="button" onClick={close} aria-label="Fermer"><X /></button></header>
      <div className="mm-theme-choice" role="group" aria-label="Thème"><button type="button" className={theme === 'light' ? 'active' : ''} aria-pressed={theme === 'light'} onClick={() => setTheme('light')}><Sun />Clair</button><button type="button" className={theme === 'dark' ? 'active' : ''} aria-pressed={theme === 'dark'} onClick={() => setTheme('dark')}><Moon />Sombre</button><button type="button" className={theme === 'system' ? 'active' : ''} aria-pressed={theme === 'system'} onClick={() => setTheme('system')}><Settings />Système</button></div>
      <Toggle icon={<Music2 />} label="Musique" checked={preferences.music} setChecked={value => setPreference('music', value)} />
      <Toggle icon={<Volume2 />} label="Effets" checked={preferences.effects} setChecked={value => setPreference('effects', value)} />
      <Toggle icon={<Vibrate />} label="Vibrations" checked={preferences.vibration} setChecked={value => setPreference('vibration', value)} />
      {newGrid ? <button className="mm-settings-link" type="button" onClick={() => { newGrid(); close() }}><RefreshCw /><span>Nouvelle grille<small>Recommencer une partie</small></span><ChevronRight /></button> : null}
      {report ? <button className="mm-settings-link" type="button" onClick={() => { close(); report() }}><ShieldAlert /><span>Signaler l’adversaire<small>Prévenir la modération</small></span><ChevronRight /></button> : null}
    </section>
  </div>
}

export function ReportPlayerOverlay({ playerName, close, submit }: {
  playerName: string
  close: () => void
  submit: (reason: 'pseudo' | 'comportement' | 'triche' | 'harcelement' | 'autre', details: string) => Promise<void>
}) {
  const [reason, setReason] = useState<'pseudo' | 'comportement' | 'triche' | 'harcelement' | 'autre'>('comportement')
  const [details, setDetails] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dialogRef = useDialogFocus<HTMLFormElement>(close)
  const send = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(null)
    try { await submit(reason, details); close() }
    catch (problem) { setError(problem instanceof Error ? problem.message : 'Signalement impossible.') }
    finally { setBusy(false) }
  }
  return <div className="mm-modal-layer mm-report-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && close()}>
    <form ref={dialogRef} className="mm-settings mm-report-panel" role="dialog" aria-modal="true" aria-label={`Signaler ${playerName}`} onSubmit={send} tabIndex={-1}>
      <header><h2>Signaler {playerName}</h2><button type="button" onClick={close} aria-label="Fermer"><X /></button></header>
      <label htmlFor="game-report-reason">Motif</label>
      <select id="game-report-reason" value={reason} onChange={event => setReason(event.target.value as typeof reason)}><option value="pseudo">Pseudo inapproprié</option><option value="comportement">Comportement</option><option value="triche">Triche</option><option value="harcelement">Harcèlement</option><option value="autre">Autre</option></select>
      <label htmlFor="game-report-details">Précisions facultatives</label>
      <textarea id="game-report-details" maxLength={500} value={details} onChange={event => setDetails(event.target.value)} placeholder="Décrivez brièvement le problème." />
      {error ? <p className="mm-account-error" role="alert">{error}</p> : null}
      <button className="mm-save-guest" type="submit" disabled={busy}>{busy ? 'Envoi…' : 'Envoyer le signalement'}</button>
    </form>
  </div>
}

export function PauseOverlay({ resume, quit }: { resume: () => void; quit: () => void }) {
  const dialogRef = useDialogFocus<HTMLElement>(resume)
  return <div className="mm-modal-layer mm-pause-layer" role="presentation"><section ref={dialogRef} className="mm-pause" role="dialog" aria-modal="true" aria-label="Partie en pause" tabIndex={-1}><Pause /><h2>Partie en pause</h2><p>Le chrono est arrêté.</p><button type="button" data-dialog-autofocus onClick={resume}>Reprendre</button><button type="button" className="secondary" onClick={quit}>Quitter la partie</button></section></div>
}
