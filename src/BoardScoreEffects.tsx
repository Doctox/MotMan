import type { CSSProperties } from 'react'
import { gridCellCoordinates, type GridDimensions } from './gridDimensions'

export type BoardScoreEffect = {
  id: string
  kind: 'letter' | 'word'
  label: string
  owner: 'player' | 'bot'
  cellIndex: number
}

export function BoardScoreEffects({ effects, columns, rows }: { effects: BoardScoreEffect[] } & GridDimensions) {
  if (!effects.length) return null

  return <div className="board-effects-layer" aria-hidden="true">
    {effects.map(effect => {
      const { row, column } = gridCellCoordinates({ columns, rows }, effect.cellIndex)
      // Letter rewards sit in the upper-right area of their cell. Word rewards
      // use the right edge of their anchor cell, then CSS pulls the whole circle
      // back inside. This keeps the reward readable even on the board boundary.
      const x = effect.kind === 'word' ? Math.min(column + 1, columns) : Math.min(column + .78, columns - .3)
      const y = effect.kind === 'word' ? row + .5 : row + .22
      return <span
        key={effect.id}
        className={`reward-bubble reward-bubble--${effect.kind} reward-bubble--${effect.owner}`}
        style={{ left: `${x / columns * 100}%`, top: `${y / rows * 100}%` } as CSSProperties}
      ><span className="reward-bubble__value">{effect.label}</span></span>
    })}
  </div>
}
