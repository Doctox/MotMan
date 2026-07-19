import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Check, Feather, PackageOpen, Palette, ShoppingBasket, Sparkles, User } from 'lucide-react'
import { assetUrl } from './assetUrl'
import {
  ANIMATIONS, AVATARS, BASKETS, FRAMES, avatarRarity,
  type CosmeticKind, type CosmeticReward, type PlayerCosmetics,
} from './cosmetics'
import { CosmeticPortrait } from './CosmeticPortrait'
import { equipServerCosmetic, openServerBasket, purchaseServerCosmetic } from './auth'

type ShopTab = 'avatars' | 'frames' | 'animations' | 'baskets'
type BasketStageState = 'idle' | 'opening' | 'revealed'

const RARITY_LABELS = {
  commun: 'Normal', singulier: 'Singulier', rare: 'Rare', precieux: 'Précieux',
  exceptionnel: 'Exceptionnel', legendaire: 'Légendaire',
} as const

const ODDS_RARITIES = ['commun', 'singulier', 'rare', 'precieux', 'exceptionnel', 'legendaire'] as const
const AVATAR_FAMILIES = [
  { kind: 'human' as const, label: 'Humains', itemLabel: 'Humain' },
  { kind: 'animal' as const, label: 'Animaux', itemLabel: 'Animal' },
  { kind: 'object' as const, label: 'Objets', itemLabel: 'Objet' },
]

function formatProbability(value: number): string {
  if (value <= 0) return '—'
  return `${value.toLocaleString('fr-FR', { minimumFractionDigits: value < 1 ? 1 : 0, maximumFractionDigits: 1 })} %`
}

function Price({ value }: { value: number }) {
  return <span className="mm-price"><Feather />{value}</span>
}

function BasketArtwork({ state }: { state: BasketStageState }) {
  return <span className={`mm-basket-picture is-${state}`} aria-hidden="true">
    <img className="mm-basket-picture-closed" src={assetUrl('/assets/shop/basket-closed.webp')} alt="" draggable={false} />
    <img className="mm-basket-picture-open" src={assetUrl('/assets/shop/basket-open.webp')} alt="" draggable={false} />
  </span>
}

function BasketReward({ reward, cosmetics }: { reward: CosmeticReward; cosmetics: PlayerCosmetics }) {
  return <span className="mm-basket-reward" aria-live="polite">
    {reward.kind === 'avatar' && reward.asset ? <CosmeticPortrait avatarId={reward.id} frameId={cosmetics.equippedFrameId} alt={reward.name} />
      : reward.kind === 'frame' ? <CosmeticPortrait avatarId={cosmetics.equippedAvatarId} frameId={reward.id} animationId={cosmetics.equippedAnimationId} alt={reward.name} />
        : <CosmeticPortrait avatarId={cosmetics.equippedAvatarId} frameId={cosmetics.equippedFrameId} animationId={reward.id} alt={reward.name} />}
    <span><small>{RARITY_LABELS[reward.rarity]}</small><strong>{reward.name}</strong></span>
  </span>
}

export function ShopPage({ cosmetics, setCosmetics, back, notify }: {
  cosmetics: PlayerCosmetics
  setCosmetics: (cosmetics: PlayerCosmetics) => void
  back: () => void
  notify: (message: string) => void
}) {
  const [tab, setTab] = useState<ShopTab>('avatars')
  const [reward, setReward] = useState<CosmeticReward | null>(null)
  const [basketState, setBasketState] = useState<BasketStageState>('idle')
  const [pendingItem, setPendingItem] = useState('')
  const basketTimerRef = useRef<number | null>(null)
  const purchasableAvatars = AVATARS.filter(avatar => avatar.availability === 'epicerie')
  const purchasableFrames = FRAMES.filter(frame => frame.availability === 'epicerie')
  const purchasableAnimations = ANIMATIONS.filter(animation => animation.availability === 'epicerie')

  useEffect(() => () => {
    if (basketTimerRef.current !== null) window.clearTimeout(basketTimerRef.current)
  }, [])

  const selectCosmetic = async (kind: CosmeticKind, id: string) => {
    if (pendingItem) return
    setPendingItem(`${kind}:${id}`)
    try {
      const owned = kind === 'avatar'
        ? cosmetics.ownedAvatarIds.includes(id)
        : kind === 'frame' ? cosmetics.ownedFrameIds.includes(id) : cosmetics.ownedAnimationIds.includes(id)
      const response = await (owned ? equipServerCosmetic(kind, id) : purchaseServerCosmetic(kind, id))
      if (!response.cosmetics) throw new Error('Collection serveur indisponible.')
      setCosmetics(response.cosmetics)
      notify(owned ? 'Style équipé' : 'Trouvaille ajoutée et équipée')
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : 'Achat impossible')
    } finally {
      setPendingItem('')
    }
  }

  const unwrapBasket = async (basketId: string) => {
    if (basketState === 'opening') return
    if (basketState === 'revealed') {
      setReward(null)
      setBasketState('idle')
      return
    }
    setBasketState('opening')
    try {
      const remote = await openServerBasket(basketId)
      if (!remote.cosmetics || !remote.reward) throw new Error('Ouverture serveur incomplète.')
      setCosmetics(remote.cosmetics)
      setReward(remote.reward)
      basketTimerRef.current = window.setTimeout(() => {
        setBasketState('revealed')
        basketTimerRef.current = null
      }, 1050)
    } catch (reason) {
      setBasketState('idle')
      notify(reason instanceof Error ? reason.message : 'Ce panier ne peut pas être ouvert')
    }
  }

  return <div className="mm-page mm-shop-page">
    <section className="mm-shop-toolbar">
      <button type="button" onClick={back} aria-label="Retour au profil"><ArrowLeft /></button>
      <b><Feather />{cosmetics.plumes.toLocaleString('fr-FR')}</b>
    </section>
    <div className="mm-shop-tabs" role="tablist" aria-label="Rayons de L’Épicerie">
      <button type="button" role="tab" aria-selected={tab === 'avatars'} className={tab === 'avatars' ? 'active' : ''} onClick={() => setTab('avatars')}><User />Avatars</button>
      <button type="button" role="tab" aria-selected={tab === 'frames'} className={tab === 'frames' ? 'active' : ''} onClick={() => setTab('frames')}><Palette />Cadres</button>
      <button type="button" role="tab" aria-selected={tab === 'animations'} className={tab === 'animations' ? 'active' : ''} onClick={() => setTab('animations')}><Sparkles />Animations</button>
      <button type="button" role="tab" aria-selected={tab === 'baskets'} className={tab === 'baskets' ? 'active' : ''} onClick={() => setTab('baskets')}><ShoppingBasket />Paniers</button>
    </div>

    {tab === 'avatars' ? <div className="mm-avatar-shelves">
      {AVATAR_FAMILIES.map(family => <section className="mm-avatar-family" aria-label={`Avatars ${family.label.toLowerCase()}`} key={family.kind}>
        <header><h2>{family.label}</h2></header>
        <div className="mm-shop-grid">
          {purchasableAvatars.filter(avatar => avatar.kind === family.kind).map(avatar => {
            const owned = cosmetics.ownedAvatarIds.includes(avatar.id)
            const equipped = cosmetics.equippedAvatarId === avatar.id
            return <article className={`mm-shop-item rarity-${avatarRarity(avatar)} ${equipped ? 'is-equipped' : ''}`} key={avatar.id}>
              <CosmeticPortrait avatarId={avatar.id} frameId="cadre-ivoire" alt={avatar.name} />
              <small>{family.itemLabel}</small><strong>{avatar.name}</strong>
              <button type="button" disabled={equipped || Boolean(pendingItem)} onClick={() => void selectCosmetic('avatar', avatar.id)}>{equipped ? <><Check />Équipé</> : owned ? 'Équiper' : <Price value={avatar.pricePlumes} />}</button>
            </article>
          })}
        </div>
      </section>)}
    </div> : null}

    {tab === 'frames' ? <section className="mm-shop-grid mm-frame-shop" aria-label="Cadres">
      {purchasableFrames.map(frame => {
        const owned = cosmetics.ownedFrameIds.includes(frame.id)
        const equipped = cosmetics.equippedFrameId === frame.id
        return <article className={`mm-shop-item rarity-${frame.rarity} ${equipped ? 'is-equipped' : ''}`} key={frame.id}>
          <CosmeticPortrait avatarId={cosmetics.equippedAvatarId} frameId={frame.id} alt={frame.name} />
          <small>{RARITY_LABELS[frame.rarity]}</small><strong>{frame.name}</strong><p>{frame.description}</p>
          <button type="button" disabled={equipped || Boolean(pendingItem)} onClick={() => void selectCosmetic('frame', frame.id)}>{equipped ? <><Check />Équipé</> : owned ? 'Équiper' : <Price value={frame.pricePlumes} />}</button>
        </article>
      })}
    </section> : null}

    {tab === 'animations' ? <section className="mm-shop-grid mm-animation-shop" aria-label="Animations de portrait">
      {purchasableAnimations.map(animation => {
        const owned = cosmetics.ownedAnimationIds.includes(animation.id)
        const equipped = cosmetics.equippedAnimationId === animation.id
        return <article className={`mm-shop-item mm-animation-shop-item rarity-${animation.rarity} ${equipped ? 'is-equipped' : ''}`} key={animation.id}>
          <CosmeticPortrait avatarId={cosmetics.equippedAvatarId} frameId={cosmetics.equippedFrameId} animationId={animation.id} alt={animation.name} previewAnimation />
          <small>{RARITY_LABELS[animation.rarity]}</small><strong>{animation.name}</strong><p>{animation.description}</p>
          <button type="button" disabled={equipped || Boolean(pendingItem)} onClick={() => void selectCosmetic('animation', animation.id)}>{equipped ? <><Check />Équipée</> : owned ? 'Équiper' : <Price value={animation.pricePlumes} />}</button>
        </article>
      })}
    </section> : null}

    {tab === 'baskets' ? <section className="mm-basket-shelf" aria-label="Paniers">
      <p>Un seul panier pour toute la collection. Chaque ouverture sans trouvaille rare améliore doucement la suivante.</p>
      {BASKETS.map(basket => <article className={`mm-basket-card cloth-${basket.cloth} is-${basketState}`} key={basket.id}>
        <header><small>Panier unique · sans doublon</small><strong>{basket.name}</strong><p>{basket.description}</p></header>
        <button className="mm-basket-stage" type="button" disabled={basketState === 'opening'} onClick={() => void unwrapBasket(basket.id)} aria-label={basketState === 'revealed' ? 'Ranger la trouvaille dans la collection' : `Ouvrir ${basket.name}`}>
          <span className="mm-basket-halo" aria-hidden="true" />
          <span className="mm-feather-cloud" aria-hidden="true">{Array.from({ length: 14 }, (_, index) => <Feather key={index} />)}</span>
          <BasketArtwork state={basketState} />
          {reward ? <BasketReward reward={reward} cosmetics={cosmetics} /> : null}
          <span className="mm-basket-action">
            {basketState === 'opening' ? <><Sparkles />Le panier s’ouvre…</>
              : basketState === 'revealed' ? <><Check />Ranger la trouvaille</>
                : <><PackageOpen />Ouvrir <Price value={basket.pricePlumes} /></>}
          </span>
        </button>
        <em>{cosmetics.basketPity > 0 ? `Chance rare renforcée · palier ${cosmetics.basketPity}` : 'Chance rare initiale'}</em>
        <details className="mm-basket-odds">
          <summary>Probabilités de ce panier</summary>
          <div>{ODDS_RARITIES.map(rarity => <span key={rarity}><i className={`rarity-${rarity}`} />{RARITY_LABELS[rarity]}<b>{formatProbability(cosmetics.basketOdds[rarity])}</b></span>)}</div>
          <small>Les chances sont recalculées selon votre collection et le palier actuel.</small>
        </details>
      </article>)}
      <small className="mm-shop-note"><Sparkles />Les paniers ne contiennent ni titre ni avantage de jeu.</small>
    </section> : null}
  </div>
}
