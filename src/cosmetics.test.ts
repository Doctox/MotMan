import { describe, expect, it } from 'vitest'
import { ANIMATIONS, AVATARS, BASKETS, FRAMES } from './cosmetics'

describe('tarifs de l’Épicerie', () => {
  it('conserve le panier unique à 999 plumes', () => {
    expect(BASKETS).toHaveLength(1)
    expect(BASKETS[0].pricePlumes).toBe(999)
  })

  it('applique les nouveaux tarifs aux avatars', () => {
    const pricesByKind = new Map([
      ['human', 1_400],
      ['animal', 1_800],
      ['object', 2_200],
    ])

    for (const avatar of AVATARS.filter(item => item.availability !== 'starter')) {
      expect(avatar.pricePlumes).toBe(pricesByKind.get(avatar.kind))
    }
  })

  it('rend chaque achat direct plus cher que le panier', () => {
    const basketPrice = BASKETS[0].pricePlumes
    const directPrices = [
      ...AVATARS.filter(item => item.availability !== 'starter').map(item => item.pricePlumes),
      ...FRAMES.filter(item => item.availability !== 'starter').map(item => item.pricePlumes),
      ...ANIMATIONS.filter(item => item.availability !== 'starter').map(item => item.pricePlumes),
    ]

    expect(directPrices.length).toBeGreaterThan(0)
    expect(Math.min(...directPrices)).toBeGreaterThan(basketPrice)
  })
})
