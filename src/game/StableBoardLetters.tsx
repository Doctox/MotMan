import { memo } from 'react'
import type { MatchState } from '../matches'
import type { RackTile } from '../rackTiles'

type Tile = RackTile

export const StableBoardLetters = memo(function StableBoardLetters({
  cellCount,
  board,
  provisional,
  failed,
  playerId,
  hiddenCell,
  draggedTileId,
}: {
  cellCount: number
  board: MatchState['board']
  provisional: Record<number, Tile>
  failed?: Record<number, string>
  playerId: string
  hiddenCell: number | null
  draggedTileId: string | null
}) {
  return <div className="confirmed-board-layer" aria-hidden="true">
    {Array.from({ length: cellCount }, (_, index) => {
      const confirmed = board[index]
      const pending = provisional[index]
      const failedLetter = failed?.[index]
      if (failedLetter) {
        return <span className="confirmed-board-letter failed-board-letter" key={index}>{failedLetter}</span>
      }
      if (confirmed && hiddenCell !== index) {
        return <span className={`confirmed-board-letter ${confirmed.playerId === playerId ? 'player-effect' : 'opponent-effect'}`} key={index}>{confirmed.letter}</span>
      }
      if (!confirmed && pending && pending.id !== draggedTileId) {
        return <span className="confirmed-board-letter provisional-effect" key={index}>{pending.letter}</span>
      }
      return <span className="confirmed-board-letter-spacer" key={index} />
    })}
  </div>
})

