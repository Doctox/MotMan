import { expect, request as playwrightRequest, test } from '@playwright/test'
import { randomUUID } from 'node:crypto'

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
  await expect(deletionPage.getByRole('link', { name: 'Demander la suppression par e-mail' })).toHaveAttribute('href', /^mailto:docteurtox@gmail\.com/)
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
