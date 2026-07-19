import avatarCatalogData from './data/avatar.catalog.json'
import { basketRarityProbabilities, basketRarityWeights as progressionRarityWeights, RARITY_ORDER } from './progressionRewards'

export type CosmeticRarity = 'commun' | 'singulier' | 'rare' | 'precieux' | 'exceptionnel' | 'legendaire'
export type CosmeticKind = 'avatar' | 'frame' | 'animation'

export type AvatarDefinition = {
  id: string
  name: string
  kind: 'human' | 'animal' | 'object'
  asset: string
  availability: 'starter' | 'epicerie' | 'easter-egg'
  pricePlumes: number
  tags: string[]
}

export type FrameDefinition = {
  id: string
  name: string
  description: string
  asset?: string
  pricePlumes: number
  rarity: CosmeticRarity
  availability: 'starter' | 'epicerie'
}

export type AnimationDefinition = {
  id: string
  name: string
  description: string
  asset?: string
  poster?: string
  pricePlumes: number
  rarity: CosmeticRarity
  availability: 'starter' | 'epicerie'
}

export type BasketDefinition = {
  id: string
  name: string
  description: string
  pricePlumes: number
  cloth: 'sage' | 'coral' | 'night'
}

export type CosmeticReward = {
  kind: CosmeticKind
  id: string
  name: string
  rarity: CosmeticRarity
  asset?: string
}

export type PlayerCosmetics = {
  version: 1
  playerId: string
  plumes: number
  ownedAvatarIds: string[]
  ownedFrameIds: string[]
  ownedAnimationIds: string[]
  equippedAvatarId: string
  equippedFrameId: string
  equippedAnimationId: string
  openedBaskets: number
  basketPity: number
  basketOdds: Record<CosmeticRarity, number>
  transactions: string[]
}

const STORAGE_KEY = 'motman-cosmetics-v1'
const WELCOME_PLUMES = 600
const ONE_TIME_PLUME_GRANTS: Record<string, { transactionId: string; amount: number }> = {
  'guest_df7ab644f1f3d21cc34116385a64d9d9': {
    transactionId: 'grant:invite-2003:2026-07-17:5000',
    amount: 5_000,
  },
}

export const AVATAR_PRICE_BY_KIND = {
  human: 1_400,
  animal: 1_800,
  object: 2_200,
} as const

export const AVATARS = (avatarCatalogData.avatars as AvatarDefinition[]).map(avatar => avatar.availability === 'starter'
  ? avatar
  : { ...avatar, pricePlumes: AVATAR_PRICE_BY_KIND[avatar.kind] })

export const FRAMES: FrameDefinition[] = [
  { id: 'cadre-ivoire', name: 'Ivoire', description: 'Le cadre MotMan classique.', pricePlumes: 0, rarity: 'commun', availability: 'starter' },
  { id: 'cadre-sauge', name: 'Sauge', description: 'Un double filet végétal apaisant.', pricePlumes: 1_200, rarity: 'commun', availability: 'epicerie' },
  { id: 'cadre-terracotta', name: 'Terre cuite', description: 'Deux lignes chaudes et délicates.', pricePlumes: 1_250, rarity: 'commun', availability: 'epicerie' },
  { id: 'cadre-encre', name: 'Encre', description: 'Un tracé profond aux reflets bleutés.', pricePlumes: 1_300, rarity: 'commun', availability: 'epicerie' },
  { id: 'cadre-laiton', name: 'Laiton', description: 'Un cercle sobre aux accents dorés.', pricePlumes: 1_350, rarity: 'commun', availability: 'epicerie' },
  { id: 'cadre-rosee', name: 'Rosée', description: 'Feuilles de sauge et perles de rosée.', asset: '/assets/frames/cadre-rosee.webp', pricePlumes: 1_600, rarity: 'singulier', availability: 'epicerie' },
  { id: 'cadre-coquelicot', name: 'Coquelicot', description: 'Pétales rouges sur ivoire.', asset: '/assets/frames/cadre-coquelicot.webp', pricePlumes: 1_700, rarity: 'singulier', availability: 'epicerie' },
  { id: 'cadre-porcelaine', name: 'Porcelaine', description: 'Fleurs cobalt et éclats de kintsugi.', asset: '/assets/frames/cadre-porcelaine.webp', pricePlumes: 1_800, rarity: 'singulier', availability: 'epicerie' },
  { id: 'cadre-herbier', name: 'Herbier', description: 'Fougères anciennes et fermoirs dorés.', asset: '/assets/frames/cadre-herbier.webp', pricePlumes: 2_100, rarity: 'rare', availability: 'epicerie' },
  { id: 'cadre-maree', name: 'Marée', description: 'Vagues sculptées et perle marine.', asset: '/assets/frames/cadre-maree.webp', pricePlumes: 2_300, rarity: 'rare', availability: 'epicerie' },
  { id: 'cadre-bibliotheque', name: 'Bibliothèque', description: 'Livres anciens et plume d’ivoire.', asset: '/assets/frames/cadre-bibliotheque.webp', pricePlumes: 2_500, rarity: 'rare', availability: 'epicerie' },
  { id: 'cadre-braise', name: 'Braise', description: 'Flammes de terre cuite et ambre.', asset: '/assets/frames/cadre-braise.webp', pricePlumes: 3_400, rarity: 'precieux', availability: 'epicerie' },
  { id: 'cadre-royal', name: 'Royal', description: 'Velours émeraude et joyaux couronnés.', asset: '/assets/frames/cadre-royal.webp', pricePlumes: 3_700, rarity: 'precieux', availability: 'epicerie' },
  { id: 'cadre-encrier', name: 'Encrier', description: 'Plumes d’or et encre nocturne.', asset: '/assets/frames/cadre-encrier.webp', pricePlumes: 4_000, rarity: 'precieux', availability: 'epicerie' },
  { id: 'cadre-clair-de-lune', name: 'Clair de lune', description: 'Croissant de lune et astres dorés.', asset: '/assets/frames/cadre-clair-de-lune.webp', pricePlumes: 5_200, rarity: 'exceptionnel', availability: 'epicerie' },
  { id: 'cadre-givre', name: 'Givre', description: 'Cristaux d’argent et saphirs glacés.', asset: '/assets/frames/cadre-givre.webp', pricePlumes: 5_600, rarity: 'exceptionnel', availability: 'epicerie' },
  { id: 'cadre-aurore', name: 'Aurore', description: 'Rubans célestes et soleil d’opale.', asset: '/assets/frames/cadre-aurore.webp', pricePlumes: 6_000, rarity: 'exceptionnel', availability: 'epicerie' },
  { id: 'cadre-constellation', name: 'Constellation', description: 'Orbite céleste et couronne d’étoiles.', asset: '/assets/frames/cadre-constellation.webp', pricePlumes: 7_800, rarity: 'legendaire', availability: 'epicerie' },
  { id: 'cadre-dragon-dore', name: 'Dragon doré', description: 'Gardien d’or serti d’émeraudes.', asset: '/assets/frames/cadre-dragon-dore.webp', pricePlumes: 8_400, rarity: 'legendaire', availability: 'epicerie' },
  { id: 'cadre-jardin-des-songes', name: 'Jardin des songes', description: 'Fleurs lumineuses et papillons de nuit.', asset: '/assets/frames/cadre-jardin-des-songes.webp', pricePlumes: 9_000, rarity: 'legendaire', availability: 'epicerie' },
]

export const NO_ANIMATION_ID = 'animation-none'

export const ANIMATIONS: AnimationDefinition[] = [
  { id: NO_ANIMATION_ID, name: 'Sans animation', description: 'Un portrait immobile et épuré.', pricePlumes: 0, rarity: 'commun', availability: 'starter' },
  { id: 'eclat', name: 'Éclat', description: 'Un reflet doré parcourt doucement le portrait.', asset: '/assets/animations/lab/eclat.png', poster: '/assets/animations/lab/eclat-poster.webp', pricePlumes: 1_200, rarity: 'commun', availability: 'epicerie' },
  { id: 'etincelle', name: 'Étincelle', description: 'Une petite lumière s’ouvre puis se referme.', asset: '/assets/animations/lab/etincelle.png', poster: '/assets/animations/lab/etincelle-poster.webp', pricePlumes: 1_250, rarity: 'commun', availability: 'epicerie' },
  { id: 'poussiere-dor', name: 'Poussière d’or', description: 'Quelques grains lumineux dérivent sans insister.', asset: '/assets/animations/lab/poussiere-dor.png', poster: '/assets/animations/lab/poussiere-dor-poster.webp', pricePlumes: 1_300, rarity: 'commun', availability: 'epicerie' },
  { id: 'souffle', name: 'Souffle', description: 'Trois courants légers effleurent le portrait.', asset: '/assets/animations/lab/souffle.png', poster: '/assets/animations/lab/souffle-poster.webp', pricePlumes: 1_350, rarity: 'commun', availability: 'epicerie' },
  { id: 'halo', name: 'Halo', description: 'Un cercle doré respire autour de l’avatar.', asset: '/assets/animations/lab/halo.png', poster: '/assets/animations/lab/halo-poster.webp', pricePlumes: 1_400, rarity: 'commun', availability: 'epicerie' },
  { id: 'lucioles', name: 'Lucioles', description: 'Quelques lumières dérivent et s’éteignent doucement.', asset: '/assets/animations/lab/lucioles.png', poster: '/assets/animations/lab/lucioles-poster.webp', pricePlumes: 1_750, rarity: 'singulier', availability: 'epicerie' },
  { id: 'brume-irisee', name: 'Brume irisée', description: 'Des nappes opalines respirent doucement.', asset: '/assets/animations/lab/brume-irisee.png', poster: '/assets/animations/lab/brume-irisee-poster.webp', pricePlumes: 1_850, rarity: 'singulier', availability: 'epicerie' },
  { id: 'constellation', name: 'Constellation', description: 'De petites étoiles apparaissent puis s’effacent.', asset: '/assets/animations/lab/constellation.png', poster: '/assets/animations/lab/constellation-poster.webp', pricePlumes: 1_950, rarity: 'singulier', availability: 'epicerie' },
  { id: 'plume', name: 'Plume', description: 'Une plume légère descend en suivant le vent.', asset: '/assets/animations/lab/plume.png', poster: '/assets/animations/lab/plume-poster.webp', pricePlumes: 2_400, rarity: 'rare', availability: 'epicerie' },
  { id: 'feuille-automne', name: 'Feuilles d’automne', description: 'Une pluie cuivrée tourbillonne doucement.', asset: '/assets/animations/lab/feuille-automne.png', poster: '/assets/animations/lab/feuille-automne-poster.webp', pricePlumes: 2_550, rarity: 'rare', availability: 'epicerie' },
  { id: 'lune-vagabonde', name: 'Lune vagabonde', description: 'Une lune nacrée passe avec ses étoiles.', asset: '/assets/animations/lab/lune-vagabonde.png', poster: '/assets/animations/lab/lune-vagabonde-poster.webp', pricePlumes: 2_700, rarity: 'rare', availability: 'epicerie' },
  { id: 'rosee', name: 'Rosée', description: 'Une goutte fait naître une onde délicate.', asset: '/assets/animations/lab/rosee.png', poster: '/assets/animations/lab/rosee-poster.webp', pricePlumes: 3_700, rarity: 'precieux', availability: 'epicerie' },
  { id: 'prisme', name: 'Prisme', description: 'Des reflets irisés glissent sur le portrait.', asset: '/assets/animations/lab/prisme.png', poster: '/assets/animations/lab/prisme-poster.webp', pricePlumes: 3_900, rarity: 'precieux', availability: 'epicerie' },
  { id: 'ecume', name: 'Écume', description: 'Un ressac discret libère des bulles nacrées.', asset: '/assets/animations/lab/ecume.png', poster: '/assets/animations/lab/ecume-poster.webp', pricePlumes: 4_100, rarity: 'precieux', availability: 'epicerie' },
  { id: 'petales', name: 'Pétales', description: 'Une pluie légère traverse naturellement le portrait.', asset: '/assets/animations/lab/petales.png', poster: '/assets/animations/lab/petales-poster.webp', pricePlumes: 5_600, rarity: 'exceptionnel', availability: 'epicerie' },
  { id: 'papillons-du-songe', name: 'Papillons du songe', description: 'De petits papillons se croisent puis repartent.', asset: '/assets/animations/lab/papillons-du-songe.png', poster: '/assets/animations/lab/papillons-du-songe-poster.webp', pricePlumes: 5_900, rarity: 'exceptionnel', availability: 'epicerie' },
  { id: 'carpes-celestes', name: 'Carpes célestes', description: 'Deux carpes lumineuses nagent de concert.', asset: '/assets/animations/lab/carpes-celestes.png', poster: '/assets/animations/lab/carpes-celestes-poster.webp', pricePlumes: 6_200, rarity: 'exceptionnel', availability: 'epicerie' },
  { id: 'oiseau-de-lumiere', name: 'L’Oiseau de lumière', description: 'La lumière prend son envol puis se disperse.', asset: '/assets/animations/lab/oiseau-de-lumiere.png', poster: '/assets/animations/lab/oiseau-de-lumiere-poster.webp', pricePlumes: 8_200, rarity: 'legendaire', availability: 'epicerie' },
  { id: 'serpent-emeraude', name: 'Serpent d’émeraude', description: 'Une lumière verte s’incarne, ondule puis s’efface.', asset: '/assets/animations/lab/serpent-emeraude.png', poster: '/assets/animations/lab/serpent-emeraude-poster.webp', pricePlumes: 8_600, rarity: 'legendaire', availability: 'epicerie' },
  { id: 'dragon-solaire', name: 'Dragon solaire', description: 'La lumière forme un dragon avant de se disperser.', asset: '/assets/animations/lab/dragon-solaire.png', poster: '/assets/animations/lab/dragon-solaire-poster.webp', pricePlumes: 9_000, rarity: 'legendaire', availability: 'epicerie' },
]

export const BASKETS: BasketDefinition[] = [
  { id: 'panier-epicerie', name: 'Panier de l’Épicerie', description: 'Un avatar, un cadre ou une animation que vous ne possédez pas encore.', pricePlumes: 999, cloth: 'sage' },
]

export function avatarRarity(avatar: AvatarDefinition): CosmeticRarity {
  if (avatar.availability === 'starter' || avatar.kind === 'human') return 'commun'
  if (avatar.kind === 'animal') return 'singulier'
  return 'rare'
}

export function getAvatar(id: string): AvatarDefinition {
  return AVATARS.find(avatar => avatar.id === id) ?? AVATARS[0]
}

export function getFrame(id: string): FrameDefinition {
  return FRAMES.find(frame => frame.id === id) ?? FRAMES[0]
}

export function getAnimation(id: string): AnimationDefinition {
  return ANIMATIONS.find(animation => animation.id === id) ?? ANIMATIONS[0]
}

function createPlayerCosmetics(playerId: string): PlayerCosmetics {
  return {
    version: 1,
    playerId,
    plumes: WELCOME_PLUMES,
    ownedAvatarIds: ['plume-motman'],
    ownedFrameIds: ['cadre-ivoire'],
    ownedAnimationIds: [NO_ANIMATION_ID],
    equippedAvatarId: 'plume-motman',
    equippedFrameId: 'cadre-ivoire',
    equippedAnimationId: NO_ANIMATION_ID,
    openedBaskets: 0,
    basketPity: 0,
    basketOdds: basketRarityProbabilities(0),
    transactions: ['welcome-credit'],
  }
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string')
}

function migratePlayerCosmetics(value: unknown, playerId: string): PlayerCosmetics | null {
  if (!value || typeof value !== 'object') return null
  const candidate = value as Partial<PlayerCosmetics>
  if (candidate.version !== 1 || candidate.playerId !== playerId) return null
  if (!isStringArray(candidate.ownedAvatarIds) || !isStringArray(candidate.ownedFrameIds)) return null
  const ownedAvatarIds = [...new Set(['plume-motman', ...candidate.ownedAvatarIds])].filter(id => AVATARS.some(avatar => avatar.id === id))
  const ownedFrameIds = [...new Set(['cadre-ivoire', ...candidate.ownedFrameIds])].filter(id => FRAMES.some(frame => frame.id === id))
  const ownedAnimationIds = [...new Set([NO_ANIMATION_ID, ...(isStringArray(candidate.ownedAnimationIds) ? candidate.ownedAnimationIds : [])])].filter(id => ANIMATIONS.some(animation => animation.id === id))
  return {
    version: 1,
    playerId,
    plumes: Math.max(0, Math.floor(candidate.plumes ?? 0)),
    ownedAvatarIds,
    ownedFrameIds,
    ownedAnimationIds,
    equippedAvatarId: ownedAvatarIds.includes(candidate.equippedAvatarId ?? '') ? candidate.equippedAvatarId! : 'plume-motman',
    equippedFrameId: ownedFrameIds.includes(candidate.equippedFrameId ?? '') ? candidate.equippedFrameId! : 'cadre-ivoire',
    equippedAnimationId: ownedAnimationIds.includes(candidate.equippedAnimationId ?? '') ? candidate.equippedAnimationId! : NO_ANIMATION_ID,
    openedBaskets: Math.max(0, Math.floor(candidate.openedBaskets ?? 0)),
    basketPity: Math.max(0, Math.min(20, Math.floor(candidate.basketPity ?? 0))),
    basketOdds: candidate.basketOdds ?? basketRarityProbabilities(candidate.basketPity ?? 0),
    transactions: isStringArray(candidate.transactions) ? candidate.transactions.slice(-300) : [],
  }
}

export function loadPlayerCosmetics(playerId: string): PlayerCosmetics {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const migrated = migratePlayerCosmetics(JSON.parse(stored), playerId)
      if (migrated) return applyOneTimePlumeGrant(migrated)
    }
  } catch {
    // Une collection locale incomplète est remplacée sans toucher au profil.
  }
  const created = createPlayerCosmetics(playerId)
  return applyOneTimePlumeGrant(created)
}

function applyOneTimePlumeGrant(cosmetics: PlayerCosmetics): PlayerCosmetics {
  const grant = ONE_TIME_PLUME_GRANTS[cosmetics.playerId]
  if (!grant || cosmetics.transactions.includes(grant.transactionId)) return cosmetics
  return savePlayerCosmetics({
    ...cosmetics,
    plumes: cosmetics.plumes + grant.amount,
    transactions: [...cosmetics.transactions, grant.transactionId].slice(-300),
  })
}

export function savePlayerCosmetics(cosmetics: PlayerCosmetics): PlayerCosmetics {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cosmetics))
  window.dispatchEvent(new CustomEvent<PlayerCosmetics>('motman:cosmetics', { detail: cosmetics }))
  return cosmetics
}

export function equipCosmetic(cosmetics: PlayerCosmetics, kind: CosmeticKind, id: string): PlayerCosmetics {
  const owned = kind === 'avatar' ? cosmetics.ownedAvatarIds : kind === 'frame' ? cosmetics.ownedFrameIds : cosmetics.ownedAnimationIds
  if (!owned.includes(id)) return cosmetics
  return savePlayerCosmetics(kind === 'avatar'
    ? { ...cosmetics, equippedAvatarId: id }
    : kind === 'frame'
      ? { ...cosmetics, equippedFrameId: id }
      : { ...cosmetics, equippedAnimationId: id })
}

export function buyCosmetic(cosmetics: PlayerCosmetics, kind: CosmeticKind, id: string): PlayerCosmetics {
  const item = kind === 'avatar'
    ? AVATARS.find(avatar => avatar.id === id)
    : kind === 'frame'
      ? FRAMES.find(frame => frame.id === id)
      : ANIMATIONS.find(animation => animation.id === id)
  if (!item || item.availability !== 'epicerie') throw new Error('Cet objet n’est pas disponible.')
  const owned = kind === 'avatar' ? cosmetics.ownedAvatarIds : kind === 'frame' ? cosmetics.ownedFrameIds : cosmetics.ownedAnimationIds
  if (owned.includes(id)) return equipCosmetic(cosmetics, kind, id)
  if (cosmetics.plumes < item.pricePlumes) throw new Error('Il vous manque quelques plumes.')
  return savePlayerCosmetics({
    ...cosmetics,
    plumes: cosmetics.plumes - item.pricePlumes,
    ownedAvatarIds: kind === 'avatar' ? [...cosmetics.ownedAvatarIds, id] : cosmetics.ownedAvatarIds,
    ownedFrameIds: kind === 'frame' ? [...cosmetics.ownedFrameIds, id] : cosmetics.ownedFrameIds,
    ownedAnimationIds: kind === 'animation' ? [...cosmetics.ownedAnimationIds, id] : cosmetics.ownedAnimationIds,
    equippedAvatarId: kind === 'avatar' ? id : cosmetics.equippedAvatarId,
    equippedFrameId: kind === 'frame' ? id : cosmetics.equippedFrameId,
    equippedAnimationId: kind === 'animation' ? id : cosmetics.equippedAnimationId,
    transactions: [...cosmetics.transactions, `buy:${kind}:${id}:${Date.now()}`].slice(-300),
  })
}

function everyUnownedReward(cosmetics: PlayerCosmetics): CosmeticReward[] {
  return [
    ...AVATARS.flatMap(avatar => avatar.availability === 'epicerie' && !cosmetics.ownedAvatarIds.includes(avatar.id)
      ? [{ kind: 'avatar' as const, id: avatar.id, name: avatar.name, rarity: avatarRarity(avatar), asset: avatar.asset }]
      : []),
    ...FRAMES.flatMap(frame => frame.availability === 'epicerie' && !cosmetics.ownedFrameIds.includes(frame.id)
      ? [{ kind: 'frame' as const, id: frame.id, name: frame.name, rarity: frame.rarity }]
      : []),
    ...ANIMATIONS.flatMap(animation => animation.availability === 'epicerie' && !cosmetics.ownedAnimationIds.includes(animation.id)
      ? [{ kind: 'animation' as const, id: animation.id, name: animation.name, rarity: animation.rarity, asset: animation.asset }]
      : []),
  ]
}

export function basketRarityWeights(pity: number): Record<CosmeticRarity, number> {
  return progressionRarityWeights(pity)
}

function drawReward(rewards: CosmeticReward[], pity: number): CosmeticReward {
  const weights = basketRarityWeights(pity)
  const groups = RARITY_ORDER.flatMap(rarity => {
    const items = rewards.filter(reward => reward.rarity === rarity)
    return items.length ? [{ rarity, items, weight: weights[rarity] }] : []
  })
  const totalWeight = groups.reduce((total, group) => total + group.weight, 0)
  let roll = Math.random() * totalWeight
  const group = groups.find(candidate => {
    roll -= candidate.weight
    return roll <= 0
  }) ?? groups[groups.length - 1]
  return group.items[Math.floor(Math.random() * group.items.length)]
}

export function openBasket(cosmetics: PlayerCosmetics, basketId: string): { cosmetics: PlayerCosmetics; reward: CosmeticReward } {
  const basket = BASKETS.find(candidate => candidate.id === basketId)
  if (!basket) throw new Error('Ce panier n’est plus disponible.')
  if (cosmetics.plumes < basket.pricePlumes) throw new Error('Il vous manque quelques plumes.')
  const rewards = everyUnownedReward(cosmetics)
  if (!rewards.length) throw new Error('Votre collection est déjà complète.')
  const reward = drawReward(rewards, cosmetics.basketPity)
  const isRareOrBetter = RARITY_ORDER.indexOf(reward.rarity) >= RARITY_ORDER.indexOf('rare')
  const nextPity = isRareOrBetter ? 0 : Math.min(20, cosmetics.basketPity + 1)
  const pending = {
    ...cosmetics,
    plumes: cosmetics.plumes - basket.pricePlumes,
    ownedAvatarIds: reward.kind === 'avatar' ? [...cosmetics.ownedAvatarIds, reward.id] : cosmetics.ownedAvatarIds,
    ownedFrameIds: reward.kind === 'frame' ? [...cosmetics.ownedFrameIds, reward.id] : cosmetics.ownedFrameIds,
    ownedAnimationIds: reward.kind === 'animation' ? [...cosmetics.ownedAnimationIds, reward.id] : cosmetics.ownedAnimationIds,
    openedBaskets: cosmetics.openedBaskets + 1,
    basketPity: nextPity,
    transactions: [...cosmetics.transactions, `basket:${basket.id}:${reward.kind}:${reward.id}:${Date.now()}`].slice(-300),
  }
  const next = savePlayerCosmetics({
    ...pending,
    basketOdds: basketRarityProbabilities(nextPity, everyUnownedReward(pending).map(item => item.rarity)),
  })
  return { cosmetics: next, reward }
}

export function grantPlumes(playerId: string, transactionId: string, amount: number): PlayerCosmetics {
  const current = loadPlayerCosmetics(playerId)
  if (amount <= 0 || current.transactions.includes(transactionId)) return current
  return savePlayerCosmetics({
    ...current,
    plumes: current.plumes + Math.floor(amount),
    transactions: [...current.transactions, transactionId].slice(-300),
  })
}

export function frameClassName(frameId: string): string {
  return `cosmetic-frame cosmetic-frame--${getFrame(frameId).id}`
}
