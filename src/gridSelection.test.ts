import { describe, expect, it } from 'vitest'
import { selectGridForPlayers, shouldYieldActiveGridClaim, type SelectionGrid } from './gridSelection'
import catalog from './data/runtime.grid.catalog.json'

const grid = (id: string, ...answers: string[]): SelectionGrid => ({
  id,
  words: answers.map(answer => ({ answer })),
})

describe('sélection anti-répétition des grilles', () => {
  it('écarte les cinq dernières grilles tant qu’une alternative existe', () => {
    const grids = Array.from({ length: 6 }, (_, index) => grid(`g${index + 1}`, `MOT${index + 1}`))
    const result = selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [grids.slice(0, 5).map(item => item.id)],
      seed: 'fresh-grid',
    })
    expect(result.grid.id).toBe('g6')
    expect(result.recentGridIds).toHaveLength(5)
  })

  it('ne retire pas une grille parce que sa réponse a déjà été vue', () => {
    const grids = [
      grid('recent-a', 'AIR', 'CHAT'),
      grid('recent-b', 'AIR', 'LUNE'),
      grid('candidate-repeated', 'AIR', 'ROSE'),
      grid('candidate-clean', 'MER', 'SOLEIL'),
    ]
    const selected = new Set(Array.from({ length: 100 }, (_, index) => selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [['recent-a', 'recent-b']],
      seed: `personal-cooldown-${index}`,
    }).grid.id))
    expect(selected).toEqual(new Set(['candidate-repeated', 'candidate-clean']))
  })

  it('ne retire aucune grille en fonction de sa popularité', () => {
    const grids = [grid('liked', 'CHAT'), grid('neutral', 'CHIEN')]
    const selected = new Set(Array.from({ length: 100 }, (_, index) => selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [[]],
      popularity: [
        { gridId: 'liked', score: 100 },
        { gridId: 'neutral', score: 0 },
      ],
      seed: `popularity-${index}`,
    }).grid.id))
    expect(selected).toEqual(new Set(['liked', 'neutral']))
  })

  it('ne retire aucune grille à cause d’un cooldown éditorial', () => {
    const grids = [grid('overused', 'AIR'), grid('clean', 'MONTAGNE')]
    const selected = new Set(Array.from({ length: 100 }, (_, index) => selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [[]],
      globalCooldownAnswers: ['AIR'],
      seed: `global-cooldown-${index}`,
    }).grid.id))
    expect(selected).toEqual(new Set(['overused', 'clean']))
  })

  it('retombe sur le catalogue complet lorsque tout a été joué', () => {
    const grids = [grid('a', 'UN'), grid('b', 'DEUX')]
    const result = selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [['a', 'b']],
      seed: 'fallback',
    })
    expect(['a', 'b']).toContain(result.grid.id)
  })

  it('écarte les grilles des parties encore actives des deux joueurs', () => {
    const grids = [grid('active-a', 'CHAT'), grid('active-b', 'CHIEN'), grid('free', 'LUNE')]
    const result = selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [[], []],
      activeGridIds: ['active-a', 'active-b'],
      seed: 'active-matches',
    })
    expect(result.grid.id).toBe('free')
  })

  it('ne réutilise une grille active que lorsque tout le catalogue est occupé', () => {
    const grids = [grid('active-a', 'CHAT'), grid('active-b', 'CHIEN')]
    const result = selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [[], []],
      activeGridIds: grids.map(item => item.id),
      seed: 'all-active-fallback',
    })
    expect(['active-a', 'active-b']).toContain(result.grid.id)
  })

  it('rend les 44 grilles publiées atteignables par le tirage en production', () => {
    const selected = new Set(Array.from({ length: 20_000 }, (_, index) => selectGridForPlayers({
      grids: catalog.grids,
      recentGridIdsByPlayer: [[]],
      globalCooldownAnswers: catalog.grids.flatMap(item => item.words.map(word => word.answer)),
      popularity: catalog.grids.map((item, itemIndex) => ({ gridId: item.id, score: itemIndex })),
      seed: `catalog-${index}`,
    }).grid.id))
    expect(selected).toEqual(new Set(catalog.grids.map(item => item.id)))
  })

  it('laisse la grille au match le plus ancien lors de deux créations simultanées', () => {
    const older = { id: 'a', createdAt: '2026-07-27T20:00:00.000Z' }
    const newer = { id: 'b', createdAt: '2026-07-27T20:00:00.100Z' }
    expect(shouldYieldActiveGridClaim(newer, [older])).toBe(true)
    expect(shouldYieldActiveGridClaim(older, [newer])).toBe(false)
  })
})
