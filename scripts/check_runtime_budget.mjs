import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve } from 'node:path'

const limits = {
  entryJavaScript: 20_000,
  runtimeCatalog: 300_000,
  runtimePolicy: 100_000,
  avatar: 100_000,
  avatarsTotal: 1_500_000,
  publicAssetsTotal: 15_000_000,
}

function assertBudget(label, actual, maximum) {
  if (actual > maximum) throw new Error(`${label}: ${actual} octets (budget ${maximum})`)
  console.log(`${label}: ${actual} / ${maximum} octets`)
}

function directorySize(directory) {
  return readdirSync(directory, { withFileTypes: true }).reduce((total, entry) => {
    const path = resolve(directory, entry.name)
    return total + (entry.isDirectory() ? directorySize(path) : statSync(path).size)
  }, 0)
}

const runtimeCatalogPath = resolve('src/data/runtime.grid.catalog.json')
const runtimePolicyPath = resolve('src/data/runtime.catalog-policy.json')
assertBudget('Catalogue runtime', statSync(runtimeCatalogPath).size, limits.runtimeCatalog)
assertBudget('Politique runtime', statSync(runtimePolicyPath).size, limits.runtimePolicy)

const avatarCatalog = JSON.parse(readFileSync(resolve('src/data/avatar.catalog.json'), 'utf8'))
let avatarsTotal = 0
for (const avatar of avatarCatalog.avatars) {
  if (!/\.(?:webp|avif)$/i.test(avatar.asset)) {
    throw new Error(`Avatar non optimisé (WebP/AVIF requis) : ${avatar.asset}`)
  }
  const assetPath = resolve('public', avatar.asset.replace(/^\//, ''))
  if (!existsSync(assetPath)) throw new Error(`Avatar introuvable : ${avatar.asset}`)
  const size = statSync(assetPath).size
  assertBudget(`Avatar ${avatar.id}`, size, limits.avatar)
  avatarsTotal += size
}
assertBudget('Avatars actifs', avatarsTotal, limits.avatarsTotal)
assertBudget('Dossier public', directorySize(resolve('public')), limits.publicAssetsTotal)

const builtIndex = readFileSync(resolve('dist/index.html'), 'utf8')
const entryMatch = builtIndex.match(/<script[^>]+src="([^"]*\/assets\/index-[^"]+\.js)"/)
if (!entryMatch) throw new Error('Entrée JavaScript du build introuvable')
const assetMarker = '/assets/'
const assetOffset = entryMatch[1].indexOf(assetMarker)
if (assetOffset < 0) throw new Error(`Chemin d'entrée JavaScript invalide : ${entryMatch[1]}`)
const entryPath = entryMatch[1].slice(assetOffset + 1)
assertBudget('Entrée JavaScript', statSync(resolve('dist', entryPath)).size, limits.entryJavaScript)
