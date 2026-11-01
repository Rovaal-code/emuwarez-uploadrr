import { InfoIcon } from '../InfoIcon'

// Los sources que llevan proveedor (el campo Proveedor solo sale con ellos).
export const PROVIDER_SOURCES = new Set(['WEB-DL'])

// Solo para FitTextPair, que pide el estilo como objeto: igual que .asist-etiqueta (asistente.css).
export const labelStyle: React.CSSProperties = {
  fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, display: 'block',
}

// Same order run_upload_checks() runs them in (services/upload_checks.py) —
// used to name the check currently in flight ("Comprobando si es
// accesible…") while its own result hasn't landed yet, since liveChecks only
// grows with COMPLETED checks: its length is the index of the one running now.
// Accessibility/integrity are no longer checked here — they're checked for
// real once the upload is queued (services/upload_queue.py's
// "verificacion_presubida" stage, which already runs MediaInfo/mkvmerge on
// the file for the nomenclature/remux steps), so a failure lands with a specific reason
// instead of duplicating that work upfront.
// A season target collapses "renameable" into one "season_pack" check
// (run_upload_checks' season branch — see upload_checks.py).
export const CHECK_STEP_ORDER = ['renameable', 'output', 'qbittorrent', 'imghosts', 'emuwarez']
export const CHECK_STEP_ORDER_SEASON = ['season_pack', 'output', 'qbittorrent', 'imghosts', 'emuwarez']
export const CHECK_STEP_PENDING_LABEL: Record<string, string> = {
  renameable: 'Comprobando si se puede renombrar…',
  season_pack: 'Comprobando el pack de temporada…',
  output: 'Comprobando el directorio de salida…',
  qbittorrent: 'Comprobando la conexión con qBittorrent…',
  imghosts: 'Comprobando el repositorio de imágenes…',
  emuwarez: 'Comprobando la conexión con eMuwarez…',
}

// Where each nomenclature field comes from (shown in the "?" tooltips).
export const FIELD_INFO = {
  title: 'Viene de Radarr/Sonarr y se traduce al español con TMDb.',
  year: 'Viene de Radarr/Sonarr.',
  season_episode: 'Temporada/episodio del release (SxxExx).',
  resolution: 'Viene de Radarr/Sonarr. El botón «Ver MediaInfo» muestra la del archivo real.',
  source: 'Prioridad: 1) nombre del archivo, 2) Radarr/Sonarr, 3) estimado con MediaInfo por bitrate (tamaño/duración) si ninguno de los dos anteriores da un source válido.',
  provider: 'Sale del nombre del archivo. Si no lo trae y el source es WEB-DL, se sugiere con TMDb (suscripción antes que alquiler, según tu prioridad).',
  video_codec: 'Se lee con MediaInfo del archivo real.',
  audio: 'Se lee con MediaInfo del archivo real (por pista).',
  subs: 'Se genera con MediaInfo del archivo real: «SUBS» si tiene pistas de subtítulos.',
  tag: 'Por defecto, el grupo de release del archivo (columna Grupo de Biblioteca); si no lo tiene, el de Ajustes. Puedes elegir otro de los guardados.',
  idioma_pista_pack: 'Esta pista de audio no trae idioma, así que el nombre del pack no la incluye. El idioma que elijas vale para todos los capítulos: entra en el nombre del pack, en el de cada capítulo y se escribe en la pista al subir.',
}

// Same value as the torrent name, just also used as the .mkv container's own
// title tag — one label reused everywhere this pairing shows up (single-file
// preview, season episode accordion, step 2 confirmation).
export const INTERNAL_TITLE_LABEL = (
  <span className="asist-fila-info">
    Título del archivo
    <InfoIcon text="Es el nombre del torrent sin acentos y con puntos: también es el título interno, el que se graba dentro del propio contenedor .mkv." />
  </span>
)
