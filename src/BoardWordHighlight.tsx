import type { CSSProperties } from 'react'
import { gridCellCoordinates, type GridDimensions } from './gridDimensions'

export type BoardWordHighlightState = {
  cells: Set<number>
  owner: 'player' | 'bot'
  direction: 'across' | 'down'
}

export function BoardWordHighlight({ highlight, columns, rows }: { highlight: BoardWordHighlightState | null } & GridDimensions) {
  if (!highlight || highlight.cells.size === 0) return null

  const coordinates = [...highlight.cells].map(cellIndex => gridCellCoordinates({ columns, rows }, cellIndex))
  const firstColumn = Math.min(...coordinates.map(cell => cell.column))
  const lastColumn = Math.max(...coordinates.map(cell => cell.column))
  const firstRow = Math.min(...coordinates.map(cell => cell.row))
  const lastRow = Math.max(...coordinates.map(cell => cell.row))

  const style = {
    left: `${firstColumn / columns * 100}%`,
    top: `${firstRow / rows * 100}%`,
    width: `${(lastColumn - firstColumn + 1) / columns * 100}%`,
    height: `${(lastRow - firstRow + 1) / rows * 100}%`,
  } as CSSProperties

  return <div className="board-word-highlight-layer" aria-hidden="true">
    <span className={`board-word-highlight board-word-highlight--${highlight.owner} board-word-highlight--${highlight.direction}`} style={style} />
  </div>
}
