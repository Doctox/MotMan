import { describe, expect, it } from 'vitest'
import { selectGridForPlayers, type SelectionGrid } from './gridSelection'

const grid = (id: string, ...answers: string[]): SelectionGrid => ({
  id,
  words: answers.map(answer => ({ answer })),
})

describe('sélection anti-répétition des grilles', () => {
  it('écarte les douze dernières grilles tant qu’une alternative existe', () => {
    const grids = Array.from({ length: 13 }, (_, index) => grid(`g${index + 1}`, `MOT${index + 1}`))
    const result = selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [grids.slice(0, 12).map(item => item.id)],
      seed: 'fresh-grid',
    })
    expect(result.grid.id).toBe('g13')
    expect(result.recentGridIds).toHaveLength(12)
  })

  it('bloque une réponse vue deux fois si une grille propre est disponible', () => {
    const grids = [
      grid('recent-a', 'AIR', 'CHAT'),
      grid('recent-b', 'AIR', 'LUNE'),
      grid('candidate-repeated', 'AIR', 'ROSE'),
      grid('candidate-clean', 'MER', 'SOLEIL'),
    ]
    const result = selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [['recent-a', 'recent-b']],
      seed: 'personal-cooldown',
    })
    expect(result.repeatedAnswersOnCooldown).toContain('AIR')
    expect(result.grid.id).toBe('candidate-clean')
  })

  it('utilise la popularité pour départager deux grilles aussi fraîches', () => {
    const grids = [grid('liked', 'CHAT'), grid('neutral', 'CHIEN')]
    const result = selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [[]],
      popularity: [
        { gridId: 'liked', score: 90 },
        { gridId: 'neutral', score: 50 },
      ],
      seed: 'popularity',
    })
    expect(result.grid.id).toBe('liked')
  })

  it('bloque temporairement une réponse éditorialement surutilisée', () => {
    const grids = [grid('overused', 'AIR'), grid('clean', 'MONTAGNE')]
    const result = selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [[]],
      globalCooldownAnswers: ['AIR'],
      seed: 'global-cooldown',
    })
    expect(result.grid.id).toBe('clean')
  })

  it('réautorise un cooldown global si aucune grille propre ne reste', () => {
    const grids = [grid('air', 'AIR'), grid('mer', 'MER')]
    const result = selectGridForPlayers({
      grids,
      recentGridIdsByPlayer: [[]],
      globalCooldownAnswers: ['AIR', 'MER'],
      seed: 'global-fallback',
    })
    expect(['air', 'mer']).toContain(result.grid.id)
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
})
