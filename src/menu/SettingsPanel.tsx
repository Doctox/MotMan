import type { ReactNode } from 'react'
import { ChevronRight, FileText, LogIn, Moon, Settings, Sun, Type, UserPlus, Vibrate, Volume2, X } from 'lucide-react'
import type { GuestIdentity } from '../playerIdentity'
import { useSensoryPreferences } from '../sensoryPreferences'
import { useDialogFocus } from '../useDialogFocus'
import type { Theme } from './types'

function ToggleRow({ icon, label, checked, setChecked }: { icon: ReactNode; label: string; checked: boolean; setChecked: (value: boolean) => void }) {
  return <label className="mm-setting-row"><span>{icon}{label}</span><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} /><i /></label>
}

export function SettingsPanel({ identity, close, openAccount, openFriends, openLegal, theme, setTheme }: { identity: GuestIdentity; close: () => void; openAccount: () => void; openFriends: () => void; openLegal: () => void; theme: Theme; setTheme: (theme: Theme) => void }) {
  const { preferences, setPreference } = useSensoryPreferences()
  const dialogRef = useDialogFocus<HTMLElement>(close)
  return <div className="mm-modal-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && close()}>
    <section ref={dialogRef} className="mm-settings" role="dialog" aria-modal="true" aria-label="Paramètres" tabIndex={-1}>
      <header><h2>Paramètres</h2><button type="button" onClick={close} aria-label="Fermer"><X /></button></header>
      <div className="mm-theme-choice" role="group" aria-label="Thème"><button type="button" className={theme === 'light' ? 'active' : ''} aria-pressed={theme === 'light'} onClick={() => setTheme('light')}><Sun />Clair</button><button type="button" className={theme === 'dark' ? 'active' : ''} aria-pressed={theme === 'dark'} onClick={() => setTheme('dark')}><Moon />Sombre</button><button type="button" className={theme === 'system' ? 'active' : ''} aria-pressed={theme === 'system'} onClick={() => setTheme('system')}><Settings />Système</button></div>
      <ToggleRow icon={<Type />} label="Texte plus grand" checked={preferences.largeText} setChecked={value => setPreference('largeText', value)} />
      <ToggleRow icon={<Volume2 />} label="Effets" checked={preferences.effects} setChecked={value => setPreference('effects', value)} />
      <ToggleRow icon={<Vibrate />} label="Vibrations" checked={preferences.vibration} setChecked={value => setPreference('vibration', value)} />
      <button className="mm-settings-link" type="button" onClick={openFriends}><UserPlus /><span>Amis<small>Ajouter · retirer · bloquer</small></span><ChevronRight /></button>
      <button className="mm-settings-link" type="button" onClick={openAccount}><LogIn /><span>{identity.accountType === 'account' ? 'Compte synchronisé' : 'Créer ou retrouver un compte'}<small>{identity.accountType === 'account' ? identity.displayName : 'Sauvegarder votre progression'}</small></span><ChevronRight /></button>
      <button className="mm-settings-link" type="button" onClick={openLegal}><FileText /><span>Informations<small>Confidentialité · conditions · crédits</small></span><ChevronRight /></button>
    </section>
  </div>
}
