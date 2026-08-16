// Calendrier du défi du jour, côté SERVEUR.
//
// La grille du jour est la même pour tout le monde : c'est le serveur qui la
// choisit, jamais le client (le client n'envoie ni gridId ni dateKey). Ce module
// lit le calendrier gravé `src/data/runtime.daily.calendar.json` — exactement le
// même fichier que `src/dailyCalendar.ts` côté app, pour qu'il n'existe qu'une
// seule source de vérité.
//
// ⚠️ L'attribut `with { type: 'json' }` est requis par Deno. Le pendant client
// (src/dailyCalendar.ts) garde l'import simple attendu par Vite : les deux
// runtimes lisent le même fichier, chacun avec sa syntaxe.

import calendarData from '../../../src/data/runtime.daily.calendar.json' with { type: 'json' }

type DailyCalendarDay = {
  date: string
  gridId: string
  theme: string | null
  difficulty?: 'easy' | 'normal' | 'hard'
}

const days = ((calendarData as { days?: DailyCalendarDay[] }).days ?? [])
const byDate = new Map(days.map(day => [day.date, day]))

const PARIS_DAY_FORMAT = new Intl.DateTimeFormat('fr-CA', {
  timeZone: 'Europe/Paris',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

/**
 * Clé de jour `YYYY-MM-DD` en Europe/Paris. Le défi bascule à minuit Paris
 * (contrat 3). Toujours calculée sur l'HORLOGE SERVEUR : une horloge client
 * avancée ne doit jamais pouvoir ouvrir le défi de demain.
 */
export function parisDateKey(instant: Date = new Date()): string {
  return PARIS_DAY_FORMAT.format(instant)
}

/**
 * Grille programmée pour ce jour, ou `null` si la date n'est pas couverte. Dans
 * ce cas l'appelant retombe sur la sélection normale du catalogue : le joueur a
 * toujours une grille, elle n'est simplement plus garantie partagée.
 */
export function dailyGridIdFor(dateKey: string): string | null {
  return byDate.get(dateKey)?.gridId ?? null
}

/** Nombre de jours programmés — utile aux journaux de démarrage. */
export const dailyCalendarSize = days.length
