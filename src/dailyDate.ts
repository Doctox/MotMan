import { serverNow } from './serverClock'

// La grille du jour et la série basculent à minuit **Europe/Paris** (contrat 3,
// MotMan_Chaine_de_production_et_Contrats.md §4). On dérive la clé de jour depuis
// un instant epoch via Intl : `fr-CA` formate en `YYYY-MM-DD`, et le fuseau
// `Europe/Paris` gère automatiquement le passage heure d'été / hiver (UTC+2 / +1).
const PARIS_DAY_FORMAT = new Intl.DateTimeFormat('fr-CA', {
  timeZone: 'Europe/Paris',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

/**
 * Clé de jour `YYYY-MM-DD` en Europe/Paris pour un instant donné (ms depuis epoch).
 * Fonction pure : même entrée → même sortie, testable sans horloge réelle.
 */
export function dailyDateKey(nowMs: number): string {
  return PARIS_DAY_FORMAT.format(new Date(nowMs))
}

/**
 * Clé de jour courante. Source de temps : `serverNow()` en priorité (offset
 * d'horloge serveur, cf. serverClock.ts), repli sur l'horloge locale si l'appel
 * échoue. Cela réserve la triche par avance d'horloge aux seuls cas hors-ligne.
 */
export function currentDailyDateKey(): string {
  return dailyDateKey(currentTimeMs())
}

function currentTimeMs(): number {
  try {
    const now = serverNow()
    if (Number.isFinite(now) && now > 0) return now
  } catch {
    // serverClock indisponible : on retombe proprement sur l'horloge locale.
  }
  return Date.now()
}
