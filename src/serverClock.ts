// A tiny server-clock offset so turn timing does not depend on the device clock.
// Many phones run with a skewed local clock; comparing it directly to the
// server's turn timestamps made a turn look already expired (or still running)
// when it was not — the player then saw "Valider" do nothing, or the turn end
// early. We measure the gap between the server's clock (sent on every match
// snapshot as `serverTime`) and the local clock, then expose serverNow() for all
// turn-timing decisions. If the server sends no time (older backend), the offset
// stays 0 and behaviour is identical to before.

let offsetMs = 0

export function noteServerTime(iso?: string | null): void {
  if (typeof iso !== 'string') return
  const serverMs = Date.parse(iso)
  if (Number.isFinite(serverMs)) offsetMs = serverMs - Date.now()
}

export function serverNow(): number {
  return Date.now() + offsetMs
}
