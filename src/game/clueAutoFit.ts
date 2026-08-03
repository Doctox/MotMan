import { useCallback, useRef } from 'react'

/* ---------------------------------------------------------------------------
   Auto-fit du texte des indices (mots-fleches) sur petits ecrans.

   Probleme : dans une grille a 7 colonnes sur un telephone compact, une case
   d'indice fait ~45 px de large. Un mot long comme « STATISTIQUE » n'y tient
   pas sur une ligne et se coupe salement (« statistiq / ue »).

   Solution : pour chaque case d'indice, on mesure le mot le plus long et on
   reduit la police juste ce qu'il faut pour qu'il tienne sur une seule ligne.
   Les indices en deux mots continuent de passer a la ligne entre les mots,
   comme avant ; seuls les mots trop longs sont legerement retrecis.

   Surete : purement cosmetique et defensif.
     - Toute exception est avalee : jamais de grille cassee.
     - On repart toujours de la taille CSS d'origine avant de mesurer, donc
       aucun effet cumulatif d'un passage a l'autre.
     - On ne fait que REDUIRE, jamais agrandir au-dela de la valeur CSS.
     - Un plancher (MIN_FONT_PX) evite tout texte illisible ; si un mot ne
       tient toujours pas a cette taille, on laisse le navigateur le couper
       (degradation douce, comportement d'origine).
--------------------------------------------------------------------------- */

const MIN_FONT_PX = 5      // en dessous, illisible -> on laisse couper naturellement
const MAX_FONT_PX = 12     // garde-fou haut (la CSS plafonne deja bien plus bas)
const EPS = 0.75           // marge anti-debordement d'un cheveu (sous-pixel)

let measureCanvas: HTMLCanvasElement | null = null

function measureWord(word: string, font: string): number {
  if (!measureCanvas) measureCanvas = document.createElement('canvas')
  const ctx = measureCanvas.getContext('2d')
  if (!ctx) return 0
  ctx.font = font
  return ctx.measureText(word).width
}

/** Texte propre de la case, hors fleche directionnelle (le <b> bas/droite). */
function directText(el: HTMLElement): string {
  let text = ''
  el.childNodes.forEach(node => {
    if (node.nodeType === Node.TEXT_NODE) text += node.textContent ?? ''
  })
  return text.trim()
}

function fitOne(el: HTMLElement): void {
  // Toujours repartir de la taille CSS : pas d'effet cumulatif.
  el.style.fontSize = ''

  const text = directText(el)
  if (!text) return

  const style = getComputedStyle(el)
  const baseSize = parseFloat(style.fontSize) || MAX_FONT_PX
  const weight = style.fontWeight || '700'
  const family = style.fontFamily || "'DM Sans', sans-serif"

  const padLeft = parseFloat(style.paddingLeft) || 0
  const padRight = parseFloat(style.paddingRight) || 0
  const available = el.clientWidth - padLeft - padRight - EPS
  if (available <= 0) return

  // Unite insecable = un « mot » entre espaces (les espaces insecables sont
  // couverts par \s) ou traits d'union (le navigateur peut couper apres un
  // trait d'union).
  const tokens = text.split(/[\s-]+/).filter(Boolean)
  if (!tokens.length) return

  const font = `${weight} ${baseSize}px ${family}`
  let widest = 0
  for (const token of tokens) {
    const w = measureWord(token, font)
    if (w > widest) widest = w
  }
  if (widest <= 0 || widest <= available) return // tient deja : on garde la taille CSS

  let next = baseSize * (available / widest)
  if (next > baseSize) next = baseSize
  if (next < MIN_FONT_PX) next = MIN_FONT_PX
  if (next < baseSize - 0.05) el.style.fontSize = `${next}px`
}

/** Ajuste toutes les cases d'indices texte presentes dans `root`. */
export function fitClueTexts(root: HTMLElement | null): void {
  if (!root) return
  try {
    const nodes = root.querySelectorAll<HTMLElement>('.clue-entry:not(.image-entry)')
    nodes.forEach(fitOne)
  } catch {
    /* cosmetique : on n'interrompt jamais le jeu */
  }
}

/**
 * Renvoie un ref-callback a poser sur le conteneur `.board`.
 * Refait l'ajustement au montage, au chargement de la police web, a chaque
 * redimensionnement de la grille, et quand une nouvelle grille est rendue.
 * Un ref-callback (et non un useEffect) pour rester compatible avec le retour
 * anticipe du composant sans enfreindre les regles des hooks.
 */
export function useClueAutoFit(): (node: HTMLElement | null) => void {
  const cleanupRef = useRef<(() => void) | null>(null)

  return useCallback((node: HTMLElement | null) => {
    if (cleanupRef.current) {
      cleanupRef.current()
      cleanupRef.current = null
    }
    if (!node) return

    let frame = 0
    let cancelled = false
    const run = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => fitClueTexts(node))
    }

    // Premier ajustement SYNCHRONE : s'applique avant le premier rendu et ne
    // depend pas de requestAnimationFrame (fiable meme si l'onglet est en
    // arriere-plan, ou rAF est suspendu). Les re-mesures ulterieures passent
    // par run() (rAF, anti-rafale).
    fitClueTexts(node)

    // La police web change les mesures une fois chargee (microtache, fiable).
    const fonts = (document as unknown as { fonts?: { ready?: Promise<unknown> } }).fonts
    if (fonts?.ready) {
      fonts.ready.then(() => { if (!cancelled) fitClueTexts(node) }).catch(() => {})
    }

    let resize: ResizeObserver | null = null
    let mutation: MutationObserver | null = null

    if (typeof ResizeObserver !== 'undefined') {
      resize = new ResizeObserver(run)
      resize.observe(node)
    } else if (typeof window !== 'undefined') {
      window.addEventListener('resize', run)
    }

    // Nouvelle grille rendue dans le meme conteneur -> re-mesurer.
    // (Nos changements de police sont des mutations d'attribut `style`, non
    //  observees ici, donc aucune boucle.)
    if (typeof MutationObserver !== 'undefined') {
      mutation = new MutationObserver(run)
      mutation.observe(node, { childList: true, subtree: true, characterData: true })
    }

    cleanupRef.current = () => {
      cancelled = true
      cancelAnimationFrame(frame)
      if (resize) resize.disconnect()
      else if (typeof window !== 'undefined') window.removeEventListener('resize', run)
      if (mutation) mutation.disconnect()
    }
  }, [])
}
