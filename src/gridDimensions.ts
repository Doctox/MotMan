export type GridDimensions = { columns: number; rows: number }
export type GridDimensionsSource = { size?: number; columns?: number; rows?: number }

function validDimension(value: number | undefined): value is number {
  return Number.isInteger(value) && Number(value) > 0
}

/**
 * Resolves the rectangular grid contract. Runtime catalogues are expected to
 * provide explicit `columns` and `rows`; `size` remains accepted only for
 * old local fixtures and migration tooling.
 */
export function resolveGridDimensions(source: GridDimensionsSource): GridDimensions {
  const columns = source.columns ?? source.size
  const rows = source.rows ?? source.size
  if (!validDimension(columns) || !validDimension(rows)) {
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
