import { expect, test } from '@playwright/test'

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
