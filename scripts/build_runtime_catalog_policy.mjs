import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const sourcePath = resolve('src/data/editorial.blacklist.json')
const targetPath = resolve('src/data/runtime.catalog-policy.json')
const catalogSourcePath = resolve('src/data/grid.catalog.json')
const catalogTargetPath = resolve('src/data/runtime.grid.catalog.json')
const source = JSON.parse(readFileSync(sourcePath, 'utf8'))
const runtime = {
  version: source.version,
  quarantinedGridIds: source.quarantinedGridIds ?? [],
  rejectedAnswers: source.rejectedAnswers ?? [],
  rejectedPairs: (source.rejectedPairs ?? []).map(({ answer, clue }) => `${answer}\u0000${clue}`),
}

writeFileSync(targetPath, `${JSON.stringify(runtime)}\n`, 'utf8')
console.log(`Politique runtime : ${runtime.quarantinedGridIds.length} grilles, ${runtime.rejectedAnswers.length} réponses, ${runtime.rejectedPairs.length} couples.`)

const catalog = JSON.parse(readFileSync(catalogSourcePath, 'utf8'))
const runtimeCatalog = {
  version: catalog.version,
  grids: catalog.grids.map(grid => ({
    id: grid.id,
    ...(grid.size ? { size: grid.size } : {}),
    ...(grid.columns ? { columns: grid.columns } : {}),
    ...(grid.rows ? { rows: grid.rows } : {}),
    clueCells: grid.clueCells,
    words: grid.words.map(word => ({
      wordId: word.wordId,
      answer: word.answer,
      clue: word.clue,
      ...(word.image ? { image: word.image } : {}),
      direction: word.direction,
      arrow: word.arrow,
      clueCell: word.clueCell,
      cells: word.cells,
    })),
  })),
}
writeFileSync(catalogTargetPath, `${JSON.stringify(runtimeCatalog)}\n`, 'utf8')
console.log(`Catalogue runtime : ${runtimeCatalog.grids.length} grilles.`)
