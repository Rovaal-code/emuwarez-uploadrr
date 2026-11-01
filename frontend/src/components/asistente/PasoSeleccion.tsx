// Paso 0: qué se sube. De una serie, qué temporadas; de una temporada, el pack
// entero o una selección de capítulos.
import type { LibraryItemResponse } from '../../types/api'
import { episodeNotReadyReason, isSeasonReady, seasonNotReadyReason } from '../../utils/libraryItem'
import { IconoAviso } from '../Iconos'
import { Tooltip } from '../Tooltip'
import type { Asistente } from './useAsistente'

export function PasoSeleccion({ a }: { a: Asistente }) {
  const {
    item, allowMultiSeason, seasons, episodes, multiSelected, setMultiSelected, seasonUploadMode, setSeasonUploadMode,
    episodeSelected, setEpisodeSelected, selError, confirmMultiSelection, confirmEpisodeSelection, confirmSeasonWhole,
  } = a

  const eligibleEpisodes = episodes.filter(ep => !episodeNotReadyReason(ep))
  const allEligibleSelected = eligibleEpisodes.length > 0
    && eligibleEpisodes.every(ep => episodeSelected.has(ep.id))

  const toggleEpisode = (episodeId: number) => {
    setEpisodeSelected(prev => {
      const next = new Set(prev)
      if (next.has(episodeId)) next.delete(episodeId); else next.add(episodeId)
      return next
    })
  }

  // Only ever touches the eligible ones — "seleccionar todos" must not appear
  // to tick a card the user can't actually upload.
  const toggleAllEpisodes = () => {
    setEpisodeSelected(allEligibleSelected ? new Set() : new Set(eligibleEpisodes.map(ep => ep.id)))
  }

  const toggleMultiSeason = (seasonId: number) => {
    setMultiSelected(prev => {
      const next = new Set(prev)
      if (next.has(seasonId)) next.delete(seasonId); else next.add(seasonId)
      return next
    })
  }

  // Step 0 for a SEASON: pick how to upload it before picking what. The whole
  // pack and the per-episode selection answer to different rules, so they are
  // two cards and not two entries of one dropdown — only one of them can be
  // unavailable, and it needs room to say why.
  const seasonPackReason = seasonNotReadyReason(item)
  const seasonModeSelection = (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {([
          {
            key: 'whole' as const,
            title: 'Temporada entera',
            body: 'Un único release con todos los capítulos. Exige tenerlos todos, que coincidan en resolución y códec de vídeo, y que todos tengan audio en castellano o, si está en otro idioma, al menos subtítulos en castellano.',
            reason: seasonPackReason,
          },
          {
            key: 'episodes' as const,
            title: 'Selección de capítulos',
            body: 'Cada capítulo se sube por separado, con su propia nomenclatura, así que pueden diferir en resolución, códec o audio. Cada uno sigue necesitando audio en castellano o, si está en otro idioma, al menos subtítulos en castellano.',
            reason: eligibleEpisodes.length === 0
              ? 'Ningún capítulo de esta temporada cumple las condiciones de subida.'
              : null,
          },
        ]).map(m => {
          const enabled = !m.reason
          const selected = seasonUploadMode === m.key
          // Tarjeta seleccionable: el mismo control que usa el resto del
          // asistente para una elección de este tipo. Añade el resaltado del
          // elegido (se queda en pantalla tras pulsarlo) y el atenuado cuando
          // un modo no está disponible.
          const card = (
            <button
              className="btn btn-secondary"
              type="button"
              disabled={!enabled}
              onClick={() => setSeasonUploadMode(m.key)}
              style={{
                padding: '14px 14px', textAlign: 'left', display: 'flex', flexDirection: 'column',
                alignItems: 'flex-start', gap: 6, height: 'auto', width: '100%', minWidth: 0, whiteSpace: 'normal',
                cursor: enabled ? 'pointer' : 'not-allowed',
                opacity: enabled ? 1 : 0.45,
                ...(selected ? { background: 'color-mix(in srgb, var(--color-primary) 18%, transparent)', borderColor: 'var(--color-primary)' } : {}),
              }}
            >
              <span style={{ fontSize: 15, fontWeight: 700 }}>{m.title}</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 400, whiteSpace: 'normal' }}>{m.body}</span>
            </button>
          )
          return enabled
            ? <div key={m.key}>{card}</div>
            : <Tooltip key={m.key} content={m.reason} style={{ width: '100%' }}>{card}</Tooltip>
        })}
      </div>

      {seasonUploadMode === 'episodes' && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, gap: 12, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, cursor: 'pointer' }}>
              <input type="checkbox" checked={allEligibleSelected} onChange={toggleAllEpisodes} />
              Seleccionar todos ({eligibleEpisodes.length})
            </label>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {episodeSelected.size} seleccionado(s)
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
            {episodes.map(ep => {
              const reason = episodeNotReadyReason(ep)
              const ready = !reason
              const selected = episodeSelected.has(ep.id)
              // Already on eMuwarez stays selectable on purpose: re-uploading a
              // better version is a legitimate thing to do, so it's a warning
              // and not a wall.
              const onEmu = ep.emu_in_catalog === 1
              const card = (
                <button
                  type="button"
                  disabled={!ready}
                  onClick={() => toggleEpisode(ep.id)}
                  style={{
                    width: '100%', padding: '12px 10px', borderRadius: 8, fontSize: 13, textAlign: 'center',
                    cursor: ready ? 'pointer' : 'not-allowed',
                    background: selected ? 'color-mix(in srgb, var(--color-primary) 18%, transparent)' : 'var(--bg-card)',
                    border: `1px solid ${selected ? 'var(--color-primary)' : 'var(--border-input)'}`,
                    color: 'var(--text-primary)', opacity: ready ? 1 : 0.45,
                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 0,
                  }}
                >
                  {/* Truncated: an episode with no number falls back to its
                      title, and a long one would blow the grid cell out. */}
                  <span style={{
                    fontWeight: 600, maxWidth: '100%', overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {ep.episode_number != null ? `E${String(ep.episode_number).padStart(2, '0')}` : ep.title}
                  </span>
                  {onEmu && (
                    <span style={{ fontSize: 11, color: 'var(--color-warning)' }}><IconoAviso /> ya en eMuwarez</span>
                  )}
                </button>
              )
              const tip = reason ?? (onEmu ? 'Ya existe en eMuwarez. Puedes subirlo igualmente (por ejemplo, una versión mejor).' : null)
              return tip
                ? <Tooltip key={ep.id} content={tip} style={{ width: '100%' }}>{card}</Tooltip>
                : <div key={ep.id}>{card}</div>
            })}
          </div>
        </div>
      )}
    </>
  )

  // Step 0 de una serie: la lista de temporadas a marcar.
  // Only a season with EVERY episode Disponible AND every episode agreeing
  // on codec/audio/idiomas/subs/resolución/source can go as a season pack
  // (build_season_pack_plan() blocks otherwise) — incomplete/inconsistent
  // ones are shown greyed out and unselectable instead of letting the user
  // pick one and fail later. isSeasonReady/seasonNotReadyReason (shared with
  // LibraryActionButtons' own "Subir" button) only know about the
  // consistency check; the "incomplete" message is layered on here.
  const selectableSeasons = seasons.filter(isSeasonReady)
  // The series' own name is redundant here (already the wizard's title) —
  // just the season part, e.g. "Temporada 1"/"Especiales".
  const seasonCardLabel = (s: LibraryItemResponse) => {
    const prefix = `${item.title} - `
    if (s.title?.startsWith(prefix)) return s.title.slice(prefix.length)
    return s.season_number === 0 ? 'Especiales' : `Temporada ${s.season_number}`
  }
  const multiSeasonChecklist = (
    <div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 10 }}>
        <input
          type="checkbox"
          checked={selectableSeasons.length > 0 && multiSelected.size === selectableSeasons.length}
          onChange={e => setMultiSelected(e.target.checked ? new Set(selectableSeasons.map(s => s.id)) : new Set())}
        />
        Seleccionar todas
      </label>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10, maxHeight: 320, overflowY: 'auto' }}>
        {seasons.map(s => {
          const ready = isSeasonReady(s)
          const reason = seasonNotReadyReason(s)
          const selected = multiSelected.has(s.id)
          const card = (
            <button
              type="button"
              disabled={!ready}
              onClick={() => toggleMultiSeason(s.id)}
              style={{
                width: '100%', padding: '16px 12px', borderRadius: 8, fontSize: 13, textAlign: 'center', cursor: ready ? 'pointer' : 'not-allowed',
                background: selected ? 'color-mix(in srgb, var(--color-primary) 18%, transparent)' : 'var(--bg-card)',
                border: `1px solid ${selected ? 'var(--color-primary)' : 'var(--border-input)'}`,
                color: 'var(--text-primary)', opacity: ready ? 1 : 0.45,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <span style={{ fontWeight: 600 }}>{seasonCardLabel(s)}</span>
            </button>
          )
          return ready ? (
            <div key={s.id}>{card}</div>
          ) : (
            <Tooltip key={s.id} content={reason} style={{ width: '100%' }}>
              {card}
            </Tooltip>
          )
        })}
      </div>
    </div>
  )

  return (
    <div className="modal-body">
      <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
        {allowMultiSeason
          ? <>Elige qué temporada(s) de <strong>{item.title}</strong> subir.</>
          : <>Elige cómo subir <strong>{item.title}</strong>.</>}
      </p>
      {allowMultiSeason ? multiSeasonChecklist : seasonModeSelection}
      {selError && <p className="text-error" style={{ marginTop: 10 }}>{selError}</p>}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
        <button
          className="btn btn-primary"
          disabled={!allowMultiSeason && seasonUploadMode === null}
          onClick={
            allowMultiSeason ? confirmMultiSelection
            : seasonUploadMode === 'episodes' ? confirmEpisodeSelection : confirmSeasonWhole
          }
          type="button"
        >Continuar</button>
      </div>
    </div>
  )
}
