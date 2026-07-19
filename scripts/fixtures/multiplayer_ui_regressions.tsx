import { createRoot } from 'react-dom/client'
import { useState, type CSSProperties } from 'react'
import { Shuffle } from 'lucide-react'
import { LeaveMatchPanel, StableBoardLetters } from '../../src/MultiplayerGame'
import '../../src/styles.css'

const board = {
  10: { letter: 'R', playerId: 'me' },
  11: { letter: 'T', playerId: 'other' },
}
const provisional = { 12: { id: 'pending-g', letter: 'G' } }

function MultiplayerUiRegressions() {
  const [selected, setSelected] = useState<string | null>(null)
  const [leaveOpen, setLeaveOpen] = useState(false)
  const [leaveResult, setLeaveResult] = useState('active')
  return <main className="app-shell multiplayer-shell">
    <button type="button" data-testid="open-async-exit" onClick={() => setLeaveOpen(true)}>Ouvrir la sortie asynchrone</button>
    <output data-testid="async-exit-result">{leaveResult}</output>
    <section className="scoreboard">
      <div className="player"><span className="avatar">AD</span><span><small>Adversaire</small><strong>12</strong></span></div>
      <div className="turn async-turn"><small>Votre tour</small><span className="turn-timer">24h</span><strong>À vous de jouer</strong></div>
      <div className="player player-you"><span className="avatar">VO</span><span><small>Vous</small><strong>18</strong></span></div>
    </section>
    <section className="board-wrap">
      <div className="board" data-testid="regression-board" style={{ '--board-columns': 7, '--board-rows': 8, '--board-aspect': '7 / 8' } as CSSProperties}>
        {Array.from({ length: 56 }, (_, index) => <div className="cell slot" key={index} />)}
        <StableBoardLetters cellCount={56} board={board} provisional={provisional} playerId="me" hiddenCell={null} draggedTileId={null} />
      </div>
    </section>
    <section className="rack-area">
      <div className="rack-heading"><strong>Vos lettres</strong><span>5 disponibles</span></div>
      <div className="rack" data-testid="regression-rack">
        {'RTNPG'.split('').map(letter => <div className="rack-slot" key={letter}><button className={`rack-letter ${selected === letter ? 'selected' : ''}`} type="button" onClick={() => setSelected(current => current === letter ? null : letter)}>{letter}</button></div>)}
        <button className="reroll-button" type="button" aria-label="Relancer les lettres"><Shuffle /></button>
      </div>
    </section>
    {leaveOpen ? <LeaveMatchPanel opponentName="Camille" isAsync cancel={() => setLeaveOpen(false)} continueLater={() => { setLeaveResult('later'); setLeaveOpen(false) }} leave={() => { setLeaveResult('forfeit'); setLeaveOpen(false) }} /> : null}
  </main>
}

createRoot(document.getElementById('root')!).render(<MultiplayerUiRegressions />)
