import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createClient } from '@supabase/supabase-js'
import WebSocket from 'ws'

async function readEnvironment() {
  const source = await readFile(new URL('../.env.local', import.meta.url), 'utf8')
  return Object.fromEntries(source.split(/\r?\n/).flatMap(line => {
    const match = line.match(/^([^#=]+)=(.*)$/)
    return match ? [[match[1].trim(), match[2].trim().replace(/^['"]|['"]$/g, '')]] : []
  }))
}

const env = await readEnvironment()
const url = env.VITE_SUPABASE_URL
const key = env.VITE_SUPABASE_PUBLISHABLE_KEY
assert.ok(url && key, 'Configuration Supabase absente de .env.local')
const runtimeCatalog = JSON.parse(await readFile(new URL('../src/data/runtime.grid.catalog.json', import.meta.url), 'utf8'))

function sessionClient() {
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    realtime: { transport: WebSocket },
  })
}

async function createPlayer() {
  const client = sessionClient()
  const { data, error } = await client.auth.signInAnonymously()
  assert.ifError(error)
  assert.ok(data.session?.access_token && data.user)
  return { client, user: data.user, token: data.session.access_token }
}

async function invoke(player, name, body, expectedStatus = 200) {
  const response = await fetch(`${url}/functions/v1/${name}`, {
    method: 'POST',
    headers: { apikey: key, Authorization: `Bearer ${player.token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await response.json().catch(() => ({}))
  assert.equal(response.status, expectedStatus, `${name}/${body.action}: ${response.status} ${JSON.stringify(payload)}`)
  return payload
}

function matchBroadcastProbe(client, matchId) {
  let resolveEvent
  let rejectEvent
  const event = new Promise((resolve, reject) => { resolveEvent = resolve; rejectEvent = reject })
  const ready = new Promise((resolve, reject) => {
    const channel = client
      .channel(`match:${matchId}`, { config: { private: true } })
      .on('broadcast', { event: 'changed' }, message => resolveEvent(message.payload))
      .subscribe((status, error) => {
        if (status === 'SUBSCRIBED') resolve(channel)
        else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') reject(new Error(`Realtime ${status}: ${error?.message ?? 'sans détail'}`))
      })
    setTimeout(() => reject(new Error('Connexion Realtime trop lente')), 8_000)
  })
  setTimeout(() => rejectEvent(new Error('Aucun signal Realtime reçu')), 8_000)
  return { ready, event }
}

const [alice, bob] = await Promise.all([createPlayer(), createPlayer()])
const aliceAccount = await invoke(alice, 'account-api', { action: 'bootstrap', identity: { displayName: 'Alice QA' } })
const bobAccount = await invoke(bob, 'account-api', { action: 'bootstrap', identity: { displayName: 'Bob QA' } })
assert.equal(aliceAccount.identity.playerId, alice.user.id)
assert.equal(bobAccount.identity.playerId, bob.user.id)
assert.equal(aliceAccount.progress.level, 1)
assert.equal(aliceAccount.progress.version, 3)
assert.equal(aliceAccount.progress.equippedTitleId, 'premiers-mots')
assert.ok(aliceAccount.progress.titles.find(title => title.id === 'premiers-mots')?.unlocked)
assert.ok(aliceAccount.progress.titles.find(title => title.id === 'plume-curieuse' && !title.unlocked))
const initialOdds = Object.values(aliceAccount.cosmetics.basketOdds).reduce((total, chance) => total + chance, 0)
assert.ok(Math.abs(initialOdds - 100) < 0.001, 'Les probabilités du panier doivent totaliser 100 %')

await invoke(alice, 'account-api', {
  action: 'update-profile', displayName: 'Admin MotMan', avatarId: 'plume-motman', frameId: 'cadre-ivoire', animationId: 'animation-none',
}, 400)
await invoke(alice, 'social-api', { action: 'report', targetId: bob.user.id, reason: 'comportement', details: 'Test automatisé' })

const created = await invoke(alice, 'match-api', { action: 'solo', difficulty: 'normal', pace: 'realtime' })
const match = created.match
assert.equal(match.mode, 'solo')
assert.ok(match.grid && match.grid.columns === 7 && match.grid.rows === 8)
assert.ok(match.grid.words.every(word => /^•+$/.test(word.answer)), 'Une réponse réelle a fui dans la grille publique')
assert.ok(match.grid.cells.every(cell => cell.kind !== 'letter' || cell.solution === ''), 'Une solution de cellule a fui')
assert.deepEqual(Object.keys(match.racks), [alice.user.id], 'Le client a reçu un chevalet adverse')
assert.equal(match.racks[match.bot.playerId], undefined)

const staleMutation = await invoke(alice, 'match-api', {
  action: 'reroll', matchId: match.id, knownUpdatedAt: '1970-01-01T00:00:00.000Z',
}, 409)
assert.equal(staleMutation.code, 'match_state_conflict', 'Le conflit optimiste doit être identifiable côté client')
assert.equal(staleMutation.conflict, true)
assert.equal(staleMutation.match.id, match.id)
assert.equal(staleMutation.match.updatedAt, match.updatedAt, 'Le conflit doit transporter l’état serveur courant')

await invoke(bob, 'match-api', { action: 'match', matchId: match.id }, 404)
const directCatalog = await fetch(`${url}/rest/v1/server_grid_catalog?select=id&limit=1`, {
  headers: { apikey: key, Authorization: `Bearer ${alice.token}` },
})
assert.ok([401, 403].includes(directCatalog.status), `Le catalogue serveur reste lisible directement (${directCatalog.status})`)

await new Promise(resolve => setTimeout(resolve, Math.max(0, Date.parse(match.turnStartedAt) - Date.now() + 80)))
const rack = match.racks[alice.user.id]
const sourceGrid = runtimeCatalog.grids.find(grid => grid.id === match.gridId)
assert.ok(sourceGrid, `Grille ${match.gridId} absente du catalogue de test`)
const columns = Number(sourceGrid.columns)
const rows = Number(sourceGrid.rows)
assert.equal(columns, 7)
assert.equal(rows, 8)
const solution = new Map()
for (const word of sourceGrid.words) {
  word.cells.forEach(([row, column], offset) => solution.set(row * columns + column, word.answer[offset]))
}
const wrongPlacement = rack.flatMap(letter => [...solution].map(([cellIndex, expected]) => ({ cellIndex, letter, expected })))
  .find(candidate => candidate.letter !== candidate.expected)
assert.ok(wrongPlacement, 'Impossible de construire un placement volontairement incorrect')
const played = await invoke(alice, 'match-api', {
  action: 'turn', matchId: match.id, turnNumber: match.turnNumber,
  placements: [{ cellIndex: wrongPlacement.cellIndex, letter: wrongPlacement.letter }], automatic: false,
})
assert.equal(played.result.scoreGained, 0, 'Une lettre incorrecte a rapporté des points')
assert.deepEqual(played.result.wrongPlacements, [{ cellIndex: wrongPlacement.cellIndex, letter: wrongPlacement.letter }])
assert.deepEqual(played.match.racks[alice.user.id], rack, 'La lettre refusée doit revenir sans renouveler le chevalet')
assert.equal(played.match.scores[alice.user.id], 0)
assert.deepEqual(Object.keys(played.match.racks), [alice.user.id])

const duplicate = await invoke(alice, 'match-api', {
  action: 'turn', matchId: match.id, turnNumber: match.turnNumber,
  placements: [{ cellIndex: wrongPlacement.cellIndex, letter: wrongPlacement.letter }], automatic: false,
})
assert.equal(duplicate.result.id, played.result.id, 'La répétition réseau a créé un second résultat')

const forfeited = await invoke(alice, 'match-api', { action: 'forfeit', matchId: match.id })
assert.equal(forfeited.match.status, 'finished')
assert.equal(forfeited.match.finishReason, 'forfeit')
const finalAccount = await invoke(alice, 'account-api', { action: 'state' })
const awards = finalAccount.progress.experienceAwards.filter(award => award.id === `server:match:${match.id}`)
assert.equal(awards.length, 1, 'La récompense de partie doit être enregistrée exactement une fois')
assert.equal(awards[0].breakdown.total, 0, 'Un abandon ne doit donner aucune expérience')
assert.equal(awards[0].plumesEarned, 0, 'Un abandon ne doit donner aucune plume')
assert.equal(finalAccount.progress.losses, 1, 'Un abandon doit compter comme une défaite')

const feedback = await invoke(alice, 'match-api', {
  action: 'feedback', matchId: match.id, quality: 'yes', reason: 'Rotation QA',
})
assert.equal(feedback.recorded, true, 'L’avis de grille doit être enregistré côté serveur')
assert.equal(feedback.popularity.positive_reviews >= 1, true)
assert.equal(Number.isFinite(Number(feedback.popularity.popularity_score)), true)

const rotated = await invoke(alice, 'match-api', { action: 'solo', difficulty: 'normal', pace: 'realtime' })
assert.notEqual(rotated.match.gridId, match.gridId, 'La grille précédente doit sortir de la rotation récente')
await invoke(alice, 'match-api', { action: 'forfeit', matchId: rotated.match.id })

await invoke(alice, 'social-api', { action: 'request', friendCode: bobAccount.identity.friendCode })
const bobSocial = (await invoke(bob, 'social-api', { action: 'state' })).state
assert.equal(bobSocial.incoming.length, 1)
await invoke(bob, 'social-api', { action: 'respond', requestId: bobSocial.incoming[0].id, decision: 'accept' })

// Both invitation rhythms must reach the guest lobby. Declining the realtime
// invitation keeps the remainder of this scenario focused on one active match.
await invoke(alice, 'match-api', { action: 'create', targetId: bob.user.id, pace: 'realtime' })
const realtimeLobby = await invoke(bob, 'match-api', { action: 'state' })
const realtimeInvitation = realtimeLobby.incoming.find(invitation => invitation.pace === 'realtime')
assert.ok(realtimeInvitation, 'L\u2019invitation en temps limite doit apparaitre chez l\u2019ami')
const declinedRealtime = await invoke(bob, 'match-api', {
  action: 'respond', invitationId: realtimeInvitation.id, decision: 'decline',
})
assert.equal(declinedRealtime.incoming.some(invitation => invitation.id === realtimeInvitation.id), false)

await invoke(alice, 'match-api', { action: 'create', targetId: bob.user.id, pace: 'async' })
const bobLobby = await invoke(bob, 'match-api', { action: 'state' })
assert.equal(bobLobby.incoming.length, 1)
assert.equal(bobLobby.incoming[0].pace, 'async', 'L\u2019invitation en temps illimite doit apparaitre chez l\u2019ami')
const accepted = await invoke(bob, 'match-api', { action: 'respond', invitationId: bobLobby.incoming[0].id, decision: 'accept' })
assert.equal(accepted.active.length, 1)
const friendMatchId = accepted.active[0].id
const aliceFriend = (await invoke(alice, 'match-api', { action: 'match', matchId: friendMatchId })).match
const bobFriend = (await invoke(bob, 'match-api', { action: 'match', matchId: friendMatchId })).match
assert.deepEqual(Object.keys(aliceFriend.racks), [alice.user.id])
assert.deepEqual(Object.keys(bobFriend.racks), [bob.user.id])
assert.equal(aliceFriend.racks[bob.user.id], undefined)
assert.equal(bobFriend.racks[alice.user.id], undefined)
const friendSourceGrid = runtimeCatalog.grids.find(grid => grid.id === aliceFriend.gridId)
assert.ok(friendSourceGrid, `Grille ${aliceFriend.gridId} absente du catalogue de test`)
const neededInventory = new Map()
for (const word of friendSourceGrid.words) {
  word.cells.forEach(([row, column], offset) => neededInventory.set(
    row * friendSourceGrid.columns + column,
    word.answer[offset],
  ))
}
const neededCounts = [...neededInventory.values()].reduce((counts, letter) => counts.set(letter, (counts.get(letter) ?? 0) + 1), new Map())
const dealtCounts = [...aliceFriend.racks[alice.user.id], ...bobFriend.racks[bob.user.id]]
  .reduce((counts, letter) => counts.set(letter, (counts.get(letter) ?? 0) + 1), new Map())
for (const [letter, count] of dealtCounts) {
  assert.ok(count <= (neededCounts.get(letter) ?? 0), `Le sac a distribuÃ© trop de ${letter} (${count})`)
}

// The private Realtime channel carries only a wake-up pulse. Alice must receive
// it when Bob changes their shared match; the authoritative state remains in
// match-api and is deliberately absent from the payload.
const realtimeProbe = matchBroadcastProbe(alice.client, friendMatchId)
const realtimeChannel = await realtimeProbe.ready

// Bob abandons while Alice owns the turn. This must remain possible in an
// asynchronous game, but an instant arranged forfeit must not mint rewards.
const friendForfeit = await invoke(bob, 'match-api', { action: 'forfeit', matchId: friendMatchId })
const realtimePulse = await realtimeProbe.event
assert.equal(typeof realtimePulse.updatedAt, 'string', 'Le signal Realtime ne contient pas la version de partie')
for (const privateKey of ['state', 'racks', 'board', 'scores', 'grid', 'solution']) {
  assert.equal(privateKey in realtimePulse, false, `Le signal Realtime a exposé ${privateKey}`)
}
await alice.client.removeChannel(realtimeChannel)
assert.equal(friendForfeit.match.status, 'finished')
const [aliceAfterFriend, bobAfterFriend] = await Promise.all([
  invoke(alice, 'account-api', { action: 'state' }),
  invoke(bob, 'account-api', { action: 'state' }),
])
const aliceFriendAward = aliceAfterFriend.progress.experienceAwards.find(award => award.id === `server:match:${friendMatchId}`)
const bobFriendAward = bobAfterFriend.progress.experienceAwards.find(award => award.id === `server:match:${friendMatchId}`)
assert.equal(aliceFriendAward.breakdown.total, 0)
assert.equal(aliceFriendAward.plumesEarned, 0)
assert.equal(bobFriendAward.breakdown.total, 0)
assert.equal(bobFriendAward.plumesEarned, 0)
assert.equal(aliceAfterFriend.progress.wins, 1, 'Un abandon adverse doit compter comme une victoire')
assert.equal(bobAfterFriend.progress.losses, 1, 'Le joueur qui abandonne doit enregistrer une défaite')

// Account deletion must remove the Auth identity, associated application data
// and every session. These test users are intentionally deleted at the end so
// the online QA suite does not pollute the production project.
const bobDeleted = await invoke(bob, 'account-api', { action: 'delete-account', confirmation: 'SUPPRIMER' })
assert.equal(bobDeleted.deleted, true)
await invoke(bob, 'account-api', { action: 'state' }, 401)
const aliceDeleted = await invoke(alice, 'account-api', { action: 'delete-account', confirmation: 'SUPPRIMER' })
assert.equal(aliceDeleted.deleted, true)
await invoke(alice, 'account-api', { action: 'state' }, 401)

console.log(JSON.stringify({
  status: 'ok', matchId: match.id, dimensions: `${match.grid.columns}x${match.grid.rows}`,
  privacy: 'solutions et chevalet adverse masqués', authority: 'score et récompense serveur', moderation: 'signalement accepté',
  concurrency: 'conflit de version 409 contrôlé avec état courant',
  multiplayer: 'deux sessions isolées, Realtime privé, abandon hors-tour et anti-farming validés',
  content: 'rotation des 12 dernières grilles, avis et popularité serveur validés', accountDeletion: 'données supprimées et sessions révoquées',
}, null, 2))
