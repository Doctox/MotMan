import { expect, request as playwrightRequest, test } from '@playwright/test'
import { randomUUID } from 'node:crypto'

test.beforeEach(async ({ page }, testInfo) => {
  if (testInfo.title.includes('tutoriel')) return
  await page.addInitScript(() => {
    localStorage.setItem('motman-first-run-tutorial', JSON.stringify({
      version: 1,
      completedAt: '2026-07-30T12:00:00.000Z',
    }))
  })
})

test('le tutoriel accompagne la première ouverture et reste rejouable', async ({ page }, testInfo) => {
  await page.goto('/')

  const tutorial = page.getByRole('dialog', { name: 'Tutoriel MotMan' })
  await expect(tutorial).toBeVisible()
  await expect(tutorial).toContainText('Chaque lettre correcte colore une case')

  await tutorial.getByRole('button', { name: 'Suivant' }).click()
  await expect(page.getByRole('heading', { name: 'Suivez les flèches' })).toBeVisible()
  await tutorial.getByRole('button', { name: 'Suivant' }).click()
  await expect(page.getByRole('heading', { name: 'Posez vos lettres, puis validez' })).toBeVisible()
  await tutorial.getByRole('button', { name: 'Suivant' }).click()
  await expect(page.getByRole('heading', { name: 'À chacun sa façon de jouer' })).toBeVisible()
  await expect(tutorial).toContainText('Solo')
  await expect(tutorial).toContainText('Normal')
  await expect(tutorial).toContainText('Classé')
  await expect(tutorial).toContainText('Amis')
  await tutorial.getByRole('button', { name: 'Suivant' }).click()
  await expect(page.getByRole('heading', { name: 'Rapide ou à reprendre plus tard' })).toBeVisible()
  await expect(tutorial).toContainText('45 s par tour')
  await expect(tutorial).toContainText('24 h par tour')

  await page.screenshot({ path: `output/quality/first-run-tutorial-${testInfo.project.name}.png`, fullPage: false })
  await tutorial.getByRole('button', { name: 'Choisir un mode' }).click()
  await expect(page).toHaveURL(/#jouer$/)
  await expect(tutorial).toBeHidden()

  await page.reload()
  await expect(page.getByRole('dialog', { name: 'Tutoriel MotMan' })).toBeHidden()
  await page.getByRole('button', { name: 'Paramètres' }).click()
  await page.getByRole('button', { name: /Revoir le tutoriel/ }).click()
  await expect(page.getByRole('dialog', { name: 'Tutoriel MotMan' })).toBeVisible()
  await page.getByRole('button', { name: 'Passer' }).click()
})

test('la navigation native reste entièrement au-dessus de la barre système Android', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Le runtime Android utilise Chromium WebView.')
  await page.goto('/')
  await page.evaluate(() => document.documentElement.classList.add('native-runtime'))
  await expect(page.locator('.mm-bottom-nav')).toBeVisible()

  const geometry = await page.evaluate(() => {
    const shell = document.querySelector<HTMLElement>('.mm-shell')
    const navigation = document.querySelector<HTMLElement>('.mm-bottom-nav')
    if (!shell || !navigation) throw new Error('Menu natif incomplet')
    return {
      viewportHeight: window.innerHeight,
      documentHeight: document.documentElement.scrollHeight,
      shellBottom: shell.getBoundingClientRect().bottom,
      navigationBottom: navigation.getBoundingClientRect().bottom,
    }
  })

  expect(geometry.documentHeight).toBeLessThanOrEqual(geometry.viewportHeight + 1)
  expect(geometry.shellBottom).toBeLessThanOrEqual(geometry.viewportHeight + 1)
  expect(geometry.navigationBottom).toBeLessThanOrEqual(geometry.viewportHeight - 4)
})

test('les informations légales restent lisibles sur mobile', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.locator('.mm-bottom-nav')).toBeVisible()
  await page.getByRole('button', { name: 'Paramètres' }).click()
  await page.getByRole('button', { name: /Informations/ }).click()

  const panel = page.getByRole('dialog', { name: 'Informations légales' })
  await expect(panel).toBeVisible()
  await expect(panel.getByRole('heading', { name: 'Politique de confidentialité' })).toBeVisible()
  await panel.getByRole('tab', { name: 'Conditions' }).click()
  await expect(panel.getByRole('heading', { name: 'Conditions d’utilisation' })).toBeVisible()
  await panel.getByRole('tab', { name: 'Crédits' }).click()
  await expect(panel.getByRole('heading', { name: 'Crédits et licences' })).toBeVisible()

  const externalFonts = await page.evaluate(() => performance.getEntriesByType('resource')
    .map(entry => entry.name)
    .filter(url => url.includes('fonts.googleapis.com') || url.includes('fonts.gstatic.com')))
  expect(externalFonts).toEqual([])
  await page.screenshot({ path: `output/quality/p4-legal-${testInfo.project.name}.png`, fullPage: true })
})

test('la suppression de compte est visible, confirmée et disponible hors de l’app', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.locator('.mm-bottom-nav')).toBeVisible()
  await page.getByRole('button', { name: 'Paramètres' }).click()
  await page.getByRole('button', { name: /Créer ou retrouver un compte|Compte synchronisé/ }).click()

  const account = page.getByRole('dialog', { name: 'Compte MotMan' })
  await expect(account).toBeVisible()
  await account.getByRole('button', { name: /Supprimer (mon compte|ce profil invité)/ }).click()
  await expect(account.getByRole('heading', { name: 'Supprimer le compte' })).toBeVisible()
  const finalDelete = account.getByRole('button', { name: 'Supprimer définitivement' })
  await expect(finalDelete).toBeDisabled()
  await account.getByLabel('Écrivez SUPPRIMER pour confirmer').fill('SUPPRIMER')
  await expect(finalDelete).toBeEnabled()
  const externalDeletionLink = account.getByRole('link', { name: 'Demander la suppression hors de l’application' })
  await expect(externalDeletionLink).toHaveAttribute('href', /legal\/suppression-compte\.html$/)
  const externalDeletionHref = await externalDeletionLink.getAttribute('href')
  expect(externalDeletionHref).toBeTruthy()
  await page.screenshot({ path: `output/quality/account-deletion-${testInfo.project.name}.png`, fullPage: false })

  const deletionPage = await page.context().newPage()
  await deletionPage.goto(externalDeletionHref!)
  await expect(deletionPage.getByRole('heading', { name: 'Supprimer votre compte' })).toBeVisible()
  // On vérifie qu'un lien mailto exploitable EST présent, sans figer l'adresse :
  // Google exige un contact joignable, pas une adresse en particulier. Le
  // 17/08/2026 le passage à contact@doctox.fr a fait échouer ce test alors que
  // la page était parfaitement conforme.
  await expect(deletionPage.getByRole('link', { name: 'Demander la suppression par e-mail' }))
    .toHaveAttribute('href', /^mailto:[^@\s]+@[^@\s]+\.[a-z]{2,}/i)
})

test('l’API locale supprime le profil et révoque sa session', async () => {
  const api = await playwrightRequest.newContext({
    baseURL: 'http://127.0.0.1:4175',
    extraHTTPHeaders: { Origin: 'http://127.0.0.1:4175' },
  })
  const playerId = `guest_${randomUUID()}`
  const bootstrap = await api.post('/api/auth/bootstrap', { data: { identity: { playerId, displayName: 'Suppression QA' } } })
  expect(bootstrap.ok()).toBe(true)

  const refused = await api.post('/api/auth/delete', { data: { confirmation: 'NON' } })
  expect(refused.status()).toBe(400)
  expect((await api.get('/api/auth/session')).ok()).toBe(true)

  const deleted = await api.post('/api/auth/delete', { data: { confirmation: 'SUPPRIMER' } })
  expect(deleted.ok()).toBe(true)
  expect(await deleted.json()).toEqual({ deleted: true })
  expect((await api.get('/api/auth/session')).status()).toBe(401)
  await api.dispose()
})

test('L’Épicerie ne monte que les animations visibles', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.locator('.mm-bottom-nav')).toBeVisible()
  await page.getByRole('button', { name: 'Profil' }).click()
  await page.getByRole('button', { name: /L’Épicerie/ }).click()
  await expect(page.locator('.mm-shop-tabs')).toBeVisible()

  expect(await page.locator('.mm-animation-shop').count()).toBe(0)
  await page.getByRole('tab', { name: 'Animations' }).click()
  const cards = page.locator('.mm-animation-shop-item')
  await expect(cards).toHaveCount(20)
  await expect.poll(() => page.locator('.mm-animation-shop .cosmetic-avatar-animation img').count()).toBeGreaterThan(0)
  const mountedAnimations = await page.locator('.mm-animation-shop .cosmetic-avatar-animation img').count()
  expect(mountedAnimations).toBeLessThan(await cards.count())

  await page.screenshot({ path: `output/quality/p4-shop-${testInfo.project.name}.png`, fullPage: false })
})

test('les derniers matchs libèrent la place quand un mode de jeu est ouvert', async ({ page }) => {
  await page.goto('/#jouer')

  const history = page.getByLabel('Historique des cinq derniers matchs')
  const historyShell = page.locator('.mm-recent-history')
  const solo = page.locator('#mm-solo-accordion > .mm-panel-heading')
  const multiplayer = page.locator('#mm-multiplayer-accordion > .mm-panel-heading')

  await expect(history).toBeVisible()
  await solo.click()
  await expect(historyShell).toHaveAttribute('aria-hidden', 'true')
  await expect(historyShell).toHaveCSS('opacity', '0')
  await solo.click()
  await expect(history).toBeVisible()
  await multiplayer.click()
  await expect(historyShell).toHaveAttribute('aria-hidden', 'true')
  await expect(historyShell).toHaveCSS('opacity', '0')
})

test('le mode classé affiche son emblème et explique la recherche en arrière-plan', async ({ page }, testInfo) => {
  await page.goto('/#jouer')
  await page.locator('#mm-multiplayer-accordion > .mm-panel-heading').click()
  await page.locator('#mm-ranked-accordion > .mm-panel-heading').click()

  const ranked = page.locator('.mm-ranked-mode')
  await expect(ranked).toBeVisible()
  await expect(ranked.locator('.mm-ranked-status img')).toHaveAttribute('src', /assets\/ranks\/rank-unranked\.png/)
  await expect(ranked.getByRole('button', { name: /Lancer la recherche/ })).toBeVisible()
  await expect(ranked).toContainText('45 s par tour')
  await expect(ranked).toContainText('La recherche continue en arrière-plan')

  await page.waitForTimeout(500)
  await page.screenshot({ path: `output/quality/ranked-mode-${testInfo.project.name}.png`, fullPage: false })
})
