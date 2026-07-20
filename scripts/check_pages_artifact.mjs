import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const distributionDirectory = resolve('dist')
const indexPath = resolve(distributionDirectory, 'index.html')
assert.ok(existsSync(indexPath), 'Le build GitHub Pages est absent : dist/index.html introuvable.')

const repositoryName = process.env.GITHUB_REPOSITORY?.split('/')[1]
const expectedBase = repositoryName ? `/${repositoryName}/` : '/'
const html = readFileSync(indexPath, 'utf8')

assert.match(html, /<div\s+id=["']root["']><\/div>/, 'Le point de montage React est absent du build.')
assert.ok(!/https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?/i.test(html), 'Le build contient une adresse de serveur local.')

const references = [...html.matchAll(/\b(?:src|href)=["']([^"']+)["']/g)]
  .map(match => match[1])
  .filter(reference => !/^(?:https?:|data:|#)/i.test(reference))

const assets = references.filter(reference => /\.(?:css|js)$/i.test(reference))
assert.ok(assets.some(reference => reference.endsWith('.js')), 'Aucun fichier JavaScript n’est chargé par la page.')
assert.ok(assets.some(reference => reference.endsWith('.css')), 'Aucun fichier CSS n’est chargé par la page.')

for (const reference of assets) {
  assert.ok(
    reference.startsWith(expectedBase),
    `Chemin incompatible avec GitHub Pages : ${reference} (préfixe attendu : ${expectedBase})`,
  )
  const relativePath = reference.slice(expectedBase.length).replace(/[?#].*$/, '')
  assert.ok(relativePath && existsSync(resolve(distributionDirectory, relativePath)), `Ressource construite introuvable : ${reference}`)
}

console.log(`Artefact GitHub Pages valide : base ${expectedBase}, ${assets.length} ressources CSS/JS vérifiées.`)
