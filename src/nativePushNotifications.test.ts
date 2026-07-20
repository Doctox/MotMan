import { describe, expect, it } from 'vitest'
import { pushNotificationRoute } from './nativePushNotifications'

describe('navigation depuis une notification native', () => {
  it('ouvre directement la partie indiquée', () => {
    expect(pushNotificationRoute({ type: 'match_turn', matchId: '4b8a3f49-c8b4-4b12-94e7-6ece8825831f' }))
      .toBe('#partie=4b8a3f49-c8b4-4b12-94e7-6ece8825831f')
  })

  it('ouvre Jouer pour une invitation sans partie créée', () => {
    expect(pushNotificationRoute({ type: 'friend_invitation', invitationId: 'invite-1' })).toBe('#jouer')
  })

  it('ouvre la partie quand une invitation est acceptée', () => {
    expect(pushNotificationRoute({ type: 'invitation_accepted', matchId: '5e748f98-c0c1-4657-a865-4399f510ced1' }))
      .toBe('#partie=5e748f98-c0c1-4657-a865-4399f510ced1')
  })

  it('ignore une destination non reconnue', () => {
    expect(pushNotificationRoute({ type: 'unknown', matchId: '../profil' })).toBeNull()
  })
})
