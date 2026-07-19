export type GridDimensions = { columns: number; rows: number }
export type GridDimensionsSource = { size?: number; columns?: number; rows?: number }

function validDimension(value: number | undefined): value is number {
  return Number.isInteger(value) && Number(value) > 0
}

/**
 * Resolves the current MotMan grid contract.
 *
 * The playable game is now 7 columns by 8 rows only. The old scalar `size`
 * field is intentionally rejected so a retired catalogue cannot slip
 * back into runtime through a legacy fallback.
 */
export function resolveGridDimensions(source: GridDimensionsSource): GridDimensions {
  const columns = source.columns
  const rows = source.rows
  if (source.size !== undefined || !validDimension(columns) || !validDimension(rows) || columns !== 7 || rows !== 8) {
    throw new Error('Dimensions de grille invalides')
  }
  return { columns, rows }
}

export function gridCellIndex(dimensions: GridDimensions, row: number, column: number): number {
  return row * dimensions.columns + column
}

export function gridCellCoordinates(dimensions: GridDimensions, index: number): { row: number; column: number } {
  return { row: Math.floor(index / dimensions.columns), column: index % dimensions.columns }
}
