import { createRoot } from 'react-dom/client'
import type { CSSProperties } from 'react'
import { BoardScoreEffects } from '../../src/BoardScoreEffects'
import '../../src/styles.css'

const columns = 9
const rows = 10
const effects = [{ id: 'pilot-edge-effect', kind: 'word' as const, label: '+9', owner: 'player' as const, cellIndex: 89 }]

function GridGeometryFixture() {
  return <main className="app-shell">
    <p className="instruction">Pilote technique · 9 colonnes × 10 lignes</p>
    <section className="board-wrap" aria-label="Grille pilote 9 par 10">
      <div className="board" data-testid="pilot-board" style={{ '--board-columns': columns, '--board-rows': rows, '--board-aspect': `${columns} / ${rows}` } as CSSProperties}>
        {Array.from({ length: columns * rows }, (_, index) => <div className={`cell ${index % 7 === 0 ? 'clue' : 'slot'}`} key={index}>{index % 7 === 0 ? <span>Indice</span> : null}</div>)}
        <BoardScoreEffects effects={effects} columns={columns} rows={rows} />
      </div>
    </section>
  </main>
}

createRoot(document.getElementById('root')!).render(<GridGeometryFixture />)
