// Paso 0: qué se sube. De una serie, qué temporadas; de una temporada, el pack
// entero o una selección de capítulos.
import { useId } from 'react'
import type { LibraryItemResponse } from '../../types/api'
import { episodeNotReadyReason, isSeasonReady, seasonNotReadyReason } from '../../utils/libraryItem'
import { IconoAviso } from '../Iconos'
import { Tooltip } from '../Tooltip'
import { MarcoPaso } from './piezas'
import type { Asistente } from './useAsistente'

export function PasoSeleccion({ a }: { a: Asistente }) {
  const {
    item, allowMultiSeason, seasons, episodes, multiSelected, setMultiSelected, seasonUploadMode, setSeasonUploadMode,
    episodeSelected, setEpisodeSelected, selError, confirmMultiSelection, confirmEpisodeSelection, confirmSeasonWhole,
  } = a
  const idMotivo = useId()

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
      <div className="asist-rejilla-modos">
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
          const motivoId = `${idMotivo}-modo-${m.key}`
          // Tarjeta seleccionable: el mismo control que usa el resto del
          // asistente para una elección de este tipo. Añade el resaltado del
          // elegido (se queda en pantalla tras pulsarlo) y el atenuado cuando
          // un modo no está disponible.
          const card = (
            <button
              className={selected ? 'btn btn-secondary asist-modo asist-modo-elegido' : 'btn btn-secondary asist-modo'}
              type="button"
              disabled={!enabled}
              aria-describedby={enabled ? undefined : motivoId}
              onClick={() => setSeasonUploadMode(m.key)}
            >
              <span className="asist-modo-titulo">{m.title}</span>
              <span className="asist-modo-cuerpo">{m.body}</span>
            </button>
          )
          // El motivo de un modo no disponible va a la vista, debajo de la tarjeta: en un tooltip solo salía al pasar
          // el ratón, y con el dedo no se veía nunca.
          return (
            <div key={m.key}>
              {card}
              {!enabled && <MotivoNoDisponible id={motivoId}>{m.reason}</MotivoNoDisponible>}
            </div>
          )
        })}
      </div>

      {seasonUploadMode === 'episodes' && (
        <div className="asist-mt-16">
          <div className="asist-fila-entre asist-mb-10">
            <label className="asist-casilla asist-t125 asist-clic">
              <input type="checkbox" checked={allEligibleSelected} onChange={toggleAllEpisodes} />
              Seleccionar todos ({eligibleEpisodes.length})
            </label>
            <span className="asist-t12 text-muted">
              {episodeSelected.size} seleccionado(s)
            </span>
          </div>
          <div className="asist-rejilla-tarjetas">
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
                  className={selected ? 'asist-opcion asist-opcion-capitulo asist-opcion-elegida' : 'asist-opcion asist-opcion-capitulo'}
                >
                  {/* Truncated: an episode with no number falls back to its
                      title, and a long one would blow the grid cell out. */}
                  <span className="asist-opcion-nombre">
                    {ep.episode_number != null ? `E${String(ep.episode_number).padStart(2, '0')}` : ep.title}
                  </span>
                  {onEmu && (
                    <span className="asist-aviso-chip"><IconoAviso /> ya en eMuwarez</span>
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
      <label className="asist-casilla asist-t13 asist-mb-10">
        <input
          type="checkbox"
          disabled={selectableSeasons.length === 0}
          checked={selectableSeasons.length > 0 && multiSelected.size === selectableSeasons.length}
          onChange={e => setMultiSelected(e.target.checked ? new Set(selectableSeasons.map(s => s.id)) : new Set())}
        />
        Seleccionar todas
      </label>
      <div className="asist-rejilla-tarjetas asist-rejilla-alta">
        {seasons.map(s => {
          const ready = isSeasonReady(s)
          const reason = seasonNotReadyReason(s)
          const selected = multiSelected.has(s.id)
          const motivoId = `${idMotivo}-temporada-${s.id}`
          return (
            <div key={s.id}>
              <button
                type="button"
                disabled={!ready}
                aria-describedby={ready ? undefined : motivoId}
                onClick={() => toggleMultiSeason(s.id)}
                className={selected ? 'asist-opcion asist-opcion-temporada asist-opcion-elegida' : 'asist-opcion asist-opcion-temporada'}
              >
                <span className="asist-negrita">{seasonCardLabel(s)}</span>
              </button>
              {!ready && reason && <MotivoNoDisponible id={motivoId}>{reason}</MotivoNoDisponible>}
            </div>
          )
        })}
      </div>
      {seasons.length > 0 && selectableSeasons.length === 0 && (
        <p className="text-muted asist-t12 asist-mt-10">
          Ninguna temporada se puede subir entera. Para subir capítulos sueltos, abre la ficha de la temporada y pulsa
          «Subir».
        </p>
      )}
    </div>
  )

  return (
    <MarcoPaso
      finPie
      pie={
        <button
          className="btn btn-primary"
          // Sin nada elegido no hay a dónde continuar: antes se pulsaba y solo entonces avisaba.
          disabled={allowMultiSeason
            ? multiSelected.size === 0
            : seasonUploadMode === null || (seasonUploadMode === 'episodes' && episodeSelected.size === 0)}
          onClick={
            allowMultiSeason ? confirmMultiSelection
            : seasonUploadMode === 'episodes' ? confirmEpisodeSelection : confirmSeasonWhole
          }
          type="button"
        >Continuar</button>
      }
    >
      <p className="text-muted asist-t12 asist-mb-12">
        {allowMultiSeason
          ? <>Elige qué temporada(s) de <strong>{item.title}</strong> subir.</>
          : <>Elige cómo subir <strong>{item.title}</strong>.</>}
      </p>
      {allowMultiSeason ? multiSeasonChecklist : seasonModeSelection}
      {selError && <p className="text-error asist-mt-10" role="alert">{selError}</p>}
    </MarcoPaso>
  )
}

// Por qué una opción del paso no se puede elegir, a la vista y enlazado al botón con aria-describedby.
function MotivoNoDisponible({ id, children }: { id: string; children: React.ReactNode }) {
  return <span id={id} className="asist-aviso-chip asist-motivo"><IconoAviso /> {children}</span>
}
