import assert from 'node:assert/strict'

const deploymentUrl = process.env.MOTMAN_DEPLOYMENT_URL
assert.ok(deploymentUrl, 'MOTMAN_DEPLOYMENT_URL est obligatoire pour vérifier le site publié.')

const attempts = 12
const retryDelayMs = 5_000
let lastError

for (let attempt = 1; attempt <= attempts; attempt += 1) {
  try {
    const pageUrl = new URL(deploymentUrl)
    pageUrl.searchParams.set('motman-ci', `${Date.now()}-${attempt}`)
    const pageResponse = await fetch(pageUrl, { redirect: 'follow', cache: 'no-store' })
    assert.equal(pageResponse.status, 200, `La page publiée répond avec le statut ${pageResponse.status}.`)

    const html = await pageResponse.text()
    assert.match(html, /<title>MotMan<\/title>/i, 'Le titre MotMan est absent de la page publiée.')
    assert.match(html, /<div\s+id=["']root["']><\/div>/, 'Le point de montage React est absent de la page publiée.')
    assert.ok(!/https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?/i.test(html), 'La page publiée contient une adresse locale.')

    const assetReferences = [...html.matchAll(/\b(?:src|href)=["']([^"']+\.(?:css|js))["']/gi)]
      .map(match => new URL(match[1], pageResponse.url))
    assert.ok(assetReferences.some(url => url.pathname.endsWith('.js')), 'Aucun JavaScript publié n’est référencé.')
    assert.ok(assetReferences.some(url => url.pathname.endsWith('.css')), 'Aucun CSS publié n’est référencé.')

    for (const assetUrl of assetReferences) {
      assetUrl.searchParams.set('motman-ci', `${Date.now()}-${attempt}`)
      const assetResponse = await fetch(assetUrl, { redirect: 'follow', cache: 'no-store' })
      assert.equal(assetResponse.status, 200, `La ressource ${assetUrl.pathname} répond avec le statut ${assetResponse.status}.`)
      const bytes = new Uint8Array(await assetResponse.arrayBuffer()).byteLength
      assert.ok(bytes > 0, `La ressource ${assetUrl.pathname} est vide.`)
    }

    console.log(`Déploiement MotMan opérationnel : ${pageResponse.url} (${assetReferences.length} ressources vérifiées).`)
    lastError = undefined
    break
  } catch (error) {
    lastError = error
    if (attempt < attempts) {
      console.warn(`Vérification ${attempt}/${attempts} non concluante : ${error.message}`)
      await new Promise(resolve => setTimeout(resolve, retryDelayMs))
    }
  }
}

if (lastError) throw lastError
