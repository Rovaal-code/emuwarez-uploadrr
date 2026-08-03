// Reference page synthesizing eMuwarez's official nomenclature spec and
// upload guidelines, PLUS — for each field — exactly where THIS APP gets
// that value from (Radarr/Sonarr, TMDb, the real file via MediaInfo,
// filename inference, or a Settings value), so a user can understand why a
// generated name looks the way it does. Purely informational, no state
// beyond which section's modal is currently open.

import { useState } from 'react'
import { CheckStatusIcon } from '../components/DetailCard'

function Mono({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: 'monospace', fontSize: 12.5, background: 'rgba(0,0,0,0.2)', padding: '10px 12px', borderRadius: 6, overflowX: 'auto', whiteSpace: 'pre' }}>
      {children}
    </div>
  )
}

// Campo -> ejemplo -> de dónde lo obtiene la aplicación (con su cadena de fallback
// real, no simplificada) — verificado contra el código actual de
// services/nomenclature.py, source_assistant.py, emu_format.py y
// media_info_service.py.
const FIELD_SOURCES: { field: string; example: string; source: string }[] = [
  {
    field: 'Título',
    example: 'La trama fenicia',
    source: 'Radarr/Sonarr (título original) → siempre se traduce al español vía TMDb (idioma configurado, por defecto es-ES). Para series/temporadas/episodios, el título es el de la SERIE (no el de la temporada). Si falla TMDb (sin API key o sin tmdb_id), se usa el título de Radarr/Sonarr tal cual.',
  },
  { field: 'Año', example: '2025', source: 'Directo de Radarr/Sonarr' },
  {
    field: 'Temporada/Episodio (SxxExx)',
    example: 'S01E01',
    source: 'Números de temporada/episodio de Sonarr, formateados como SxxExx. Solo aparece para series/temporadas/episodios.',
  },
  {
    field: 'Resolución',
    example: '2160p 4K UHD',
    source: 'Perfil de calidad de Radarr/Sonarr ("quality.name"), normalizado a la nomenclatura eMuwarez (ver tabla técnica abajo). No se recalcula con MediaInfo.',
  },
  {
    field: 'Proveedor',
    example: 'AMZN',
    source: 'Solo se busca cuando el Source es WEB-DL. 1º se busca el código en el propio nombre del archivo (AMZN, MA, DSNP, HMAX…). Si no aparece, en el asistente de subida se consulta TMDb (proveedores de streaming disponibles en tu región) y se elige según tu orden de prioridad configurado. Opcional: si no se encuentra por ningún lado, se omite.',
  },
  {
    field: 'Source',
    example: 'WEB-DL',
    source: 'Perfil de calidad de Radarr/Sonarr. Si falta o no es válido, el asistente de subida lo estima leyendo el archivo real con la Internal Source Tool (MediaInfo + FFprobe + MKVToolNix); se avisa cuando el valor viene estimado.',
  },
  {
    field: 'DV / HDR',
    example: 'DV HDR',
    source: 'MediaInfo del archivo real (campos HDR_Format / Format_Profile) cuando el archivo es accesible; si no, el dato que ya trae Radarr/Sonarr de su propio análisis.',
  },
  {
    field: 'Códec de vídeo',
    example: 'HEVC',
    source: 'MediaInfo del archivo real (distingue AVC/HEVC del genérico H264/H265 frente a x264/x265 del encoder) cuando el archivo es accesible; si no, el códec que ya trae Radarr/Sonarr.',
  },
  {
    field: 'Audio (idioma + códec + canales)',
    example: 'ESP DD+ Atmos 5.1',
    source: 'MediaInfo del archivo real, pista a pista (idioma, códec y canales de cada pista de audio) — aplica las reglas DUAL/MULTI/ESP-ING según cuántos idiomas haya. Si el archivo no es accesible, se usa el resumen agregado que ya trae Radarr/Sonarr (sin distinguir pistas).',
  },
  {
    field: 'Subtítulos (SUBS)',
    example: 'SUBS',
    source: 'MediaInfo del archivo real: aparece "SUBS" si hay alguna pista de subtítulos, sin más lógica de idioma o cantidad.',
  },
  {
    field: 'Tag / Grupo',
    example: 'EMUWAREZ',
    source: 'Ajustes de la aplicación (tag de subida configurado). Si no hay ninguno configurado, se usa "EMUWAREZ" por defecto.',
  },
]

const RESOLUTION_ROWS: [string, string][] = [
  ['Full Ultra HD 8k', '4320p 8K FUHD'],
  ['Ultra HD 4k', '2160p 4K UHD'],
  ['Full HD', '1080p'],
  ['HD', '720p'],
  ['SD', '576p'],
  ['SD', '540p'],
  ['SD', '480p'],
]

const SOURCE_ROWS: [string, string][] = [
  ['Full BD', 'FBD'],
  ['Full DVD', 'FDVD'],
  ['BD Remux', 'BDRemux'],
  ['BD Rip', 'BluRay'],
  ['Micro HD', 'MHD o BluRay'],
  ['Web DL', 'WEB-DL'],
  ['Web Rip', 'WEBRIP'],
  ['HDTV', 'HDTV'],
  ['DVD', 'SD (si no se sabe el formato del vídeo, se omite)'],
]

const VIDEO_CODEC_ROWS: [string, string][] = [
  ['MPEG-4', 'MPEG'],
  ['H264', 'AVC'],
  ['VC-1', 'VC-1'],
  ['H265', 'HEVC'],
  ['x264', 'x264'],
  ['x265', 'x265'],
  ['AV1', 'AV1'],
  ['VP8', 'VP8'],
  ['VP9', 'VP9'],
  ['H266', 'VVC'],
]

const HDR_ROWS: [string, string][] = [
  ['Dolby Vision', 'DV'],
  ['HDR5/10', 'HDR'],
  ['Dolby Vision HDR', 'DV HDR'],
]

const LANGUAGE_ROWS: [string, string][] = [
  ['Castellano', 'ESP'],
  ['Latino', 'LAT'],
  ['Inglés', 'ING'],
  ['Francés', 'FRA'],
  ['Alemán', 'ALE'],
  ['Japonés', 'JAP'],
  ['Coreano', 'COR'],
  ['Solo V.O.', 'V.O. ING'],
  ['V.O. sin doblaje ESP pero con subs ESP', 'VOSE ING'],
  ['V.O. ING + ESP con códecs iguales', 'DUAL'],
  ['2 o 3 idiomas (ej. ESP+ITA)', 'ESP-ITA'],
  ['4 idiomas o más', 'MULTI'],
  ['Comentarios del director', 'ING-COM'],
]

const AUDIO_CODEC_ROWS: [string, string][] = [
  ['AAC', 'AAC'],
  ['AAC Low Complexity', 'AAC LC'],
  ['AAC Low Delay', 'AAC LD'],
  ['AAC High Efficiency', 'AAC HE'],
  ['AC3 (Dolby Digital)', 'DD'],
  ['E-AC3 (Dolby Digital Plus)', 'DD+'],
  ['Dolby Atmos', 'Atmos'],
  ['Dolby TrueHD', 'TrueHD'],
  ['Dolby Surround EX', 'EX'],
  ['DTS-HD Master Audio', 'DTS-HD MA'],
  ['DTS-HD High Resolution Audio', 'DTS-HD HRA'],
  ['DTS:X', 'DTS:X'],
  ['PCM', 'PCM'],
  ['MLP FBA', 'MLP'],
  ['MP3', 'MP3'],
  ['OPUS', 'OPUS'],
  ['ALAC', 'ALAC'],
  ['FLAC', 'FLAC'],
]

// Prioridad de calidad de los códecs de audio, de mejor a peor.
//
// OJO: es una copia de _AUDIO_CODEC_QUALITY en
// services/emu_format.py. El frontend no puede llamar a Python, así que la
// copia es inevitable, pero si tocas una TIENES que tocar la otra: esta tabla
// documenta lo que hace aquella, y una guía que miente es peor que ninguna.
const AUDIO_QUALITY_ROWS: [string, string][] = [
  ['PCM', 'Sin comprimir'],
  ['MLP', 'Sin pérdida'],
  ['TrueHD', 'Sin pérdida'],
  ['DTS-HD MA', 'Sin pérdida'],
  ['FLAC', 'Sin pérdida'],
  ['ALAC', 'Sin pérdida'],
  ['DTS:X', 'Objetos, con pérdida'],
  ['DTS-HD HRA', 'Alta resolución, con pérdida'],
  ['DD+', 'Con pérdida'],
  ['DTS', 'Con pérdida'],
  ['DD', 'Con pérdida'],
  ['AAC LC / AAC HE / AAC LD / AAC', 'Con pérdida'],
  ['OPUS', 'Con pérdida'],
  ['MP3', 'Con pérdida'],
]

const CHANNEL_ROWS: [string, string][] = [
  ['Mudo', 'Mudo'],
  ['Un canal', 'Mono'],
  ['Dos canales', '2.0'],
  ['Tres canales', '3.0'],
  ['Cuatro canales', '3.1'],
  ['Cinco canales', '5.0'],
  ['Seis canales', '5.1'],
  ['Siete canales', '6.1'],
  ['Ocho canales', '7.1'],
]

const EXAMPLES = [
  'Hora punta 1998 1080p BluRay x264 ESP DD 5.1 ING DTS ES 5.1 ING-COM DD 2.0 SUBS-EMUWAREZ',
  'La trama fenicia 2025 1080p MA WEB-DL x264 ESP DD+ 5.1 ING DD+ Atmos 5.1 SUBS-EMUWAREZ',
  'Brave - Indomable 2012 2160p 4K UHD AV1 MULTI DD 5.1 SUBS - EMUWAREZ',
  'La trama fenicia 2025 2160p 4K UHD MA WEB-DL DV HDR HEVC ESP DD+ 5.1 ING DD+ Atmos 5.1 SUBS-EMUWAREZ',
  'Raíces profundas 1953 1080p BDRemux AVC ESP MLP TrueHD 2.0 ING DD 2.0 SUBS-MATTS',
  'Anacleto: Agente secreto 2015 1080p BDRemux AVC ESP-CAT TrueHD 5.1 SUBS-MATTS',
  'Upload S01 2020 1080p AMZN WEB-DL AVC DUAL DD+ 5.1 SUBS-EMUWAREZ',
  'It: Bienvenidos a Derry S01E01 2025 1080p WEB-DL HBO AVC DUAL DD+ 5.1 SUBS-EMUWAREZ',
]

function TwoColTable({ head, rows }: { head: [string, string]; rows: [string, string][] }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table" style={{ fontSize: 12.5 }}>
        <thead><tr><th>{head[0]}</th><th>{head[1]}</th></tr></thead>
        <tbody>
          {rows.map(([a, b], i) => (
            <tr key={i}><td>{a}</td><td style={{ fontFamily: 'monospace' }}>{b}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FormulaContent() {
  return (
    <>
      <p style={{ fontSize: 12.5, marginTop: 0 }}>
        Cada elemento se identifica entre corchetes, que se omiten en el nombre real del fichero y en el título del aporte.
        El proveedor (cuando se conoce) va entre la resolución y el source.
      </p>
      <Mono>
{`[Título] [Año] [Resolución] [Proveedor] [Source] [DV/HDR] [Códec vídeo] [Audio: idioma+códec+canales] [SUBS] - [Grupo/Uploader]`}
      </Mono>
      <p style={{ fontSize: 12.5, marginTop: 10, marginBottom: 0 }}>
        Para series de TV, la temporada/episodio (<code>S01</code> o <code>S01E03</code>) se añade justo antes del año.
        Para el nombre del archivo <code>.mkv</code> se usa el mismo esquema cambiando los espacios por puntos.
      </p>
    </>
  )
}

function FieldSourcesContent() {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table" style={{ fontSize: 12.5 }}>
        <thead><tr><th>Campo</th><th>Ejemplo</th><th>De dónde lo obtiene la aplicación</th></tr></thead>
        <tbody>
          {FIELD_SOURCES.map(f => (
            <tr key={f.field}>
              <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>{f.field}</td>
              <td style={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{f.example}</td>
              <td>{f.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TechSpecsContent() {
  return (
    <>
      <p style={{ fontSize: 12.5, marginTop: 0 }}>
        Tablas oficiales del tracker. La aplicación aplica estas mismas equivalencias al leer MediaInfo del archivo real
        (o el dato de Radarr/Sonarr cuando el archivo no es accesible).
      </p>

      <p style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--text-muted)', marginTop: 18, marginBottom: 8 }}>Resolución</p>
      <TwoColTable head={['MediaInfo', 'Nombre']} rows={RESOLUTION_ROWS} />

      <p style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--text-muted)', marginTop: 18, marginBottom: 8 }}>Formato (Source)</p>
      <TwoColTable head={['MediaInfo', 'Nombre']} rows={SOURCE_ROWS} />

      <p style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--text-muted)', marginTop: 18, marginBottom: 8 }}>Códec de vídeo</p>
      <p style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 0, marginBottom: 8 }}>
        Ojo: H264→AVC y x264→x264 son distintos (códec genérico vs. encoder concreto). Igual con H265→HEVC vs. x265→x265.
      </p>
      <TwoColTable head={['MediaInfo', 'Nombre']} rows={VIDEO_CODEC_ROWS} />

      <p style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--text-muted)', marginTop: 18, marginBottom: 8 }}>Dolby Vision / HDR</p>
      <p style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 0, marginBottom: 8 }}>Se coloca delante del códec de vídeo.</p>
      <TwoColTable head={['MediaInfo', 'Nombre']} rows={HDR_ROWS} />

      <p style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--text-muted)', marginTop: 18, marginBottom: 8 }}>Idioma de audio</p>
      <TwoColTable head={['MediaInfo', 'Nombre']} rows={LANGUAGE_ROWS} />

      <p style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--text-muted)', marginTop: 18, marginBottom: 8 }}>Códec de audio</p>
      <TwoColTable head={['MediaInfo', 'Nombre']} rows={AUDIO_CODEC_ROWS} />

      <p style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--text-muted)', marginTop: 18, marginBottom: 8 }}>Prioridad de audio</p>
      <p style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 0, marginBottom: 8 }}>
        Cuando un mismo idioma viene en varias pistas, el nombre se queda con una sola: la de mejor calidad.
        El nombre dice qué vas a oír, no cuántas pistas trae el archivo. La ficha técnica sí las sigue
        mostrando todas.
      </p>
      <TwoColTable head={['Códec', 'Tipo']} rows={AUDIO_QUALITY_ROWS} />
      <div style={{ fontSize: 12, marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div>
          Dos pistas japonesas, TrueHD y DD:
          <br /><Mono>JAP TrueHD 5.1 JAP DD 5.1</Mono> → <Mono>JAP TrueHD 5.1</Mono>
        </div>
        <div>
          Mismo códec y distintos canales, gana el que más tiene:
          <br /><Mono>ESP DD 5.1 ESP DD 2.0</Mono> → <Mono>ESP DD 5.1</Mono>
        </div>
        <div>
          Atmos desempata dentro del mismo códec, porque es una capa por encima y no un códec aparte:
          <br /><Mono>ING DD+ 5.1 ING DD+ Atmos 5.1</Mono> → <Mono>ING DD+ Atmos 5.1</Mono>
        </div>
        <div>
          Idiomas distintos no se tocan, y si comparten códec y canales se juntan:
          <br /><Mono>ESP TrueHD 5.1 CAT TrueHD 5.1</Mono> → <Mono>ESP-CAT TrueHD 5.1</Mono>
        </div>
      </div>

      <p style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--text-muted)', marginTop: 18, marginBottom: 8 }}>Canales de audio</p>
      <TwoColTable head={['MediaInfo', 'Nombre']} rows={CHANNEL_ROWS} />

      <p style={{ fontSize: 12.5, marginTop: 18, marginBottom: 0 }}>
        <strong>Subtítulos:</strong> cualquier pista de subtítulos, en cualquier idioma, se indica simplemente como <code>SUBS</code>.
      </p>
    </>
  )
}

function ExamplesContent() {
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {EXAMPLES.map((ex, i) => <Mono key={i}>{ex}</Mono>)}
    </div>
  )
}

function RulesContent() {
  return (
    <ul style={{ fontSize: 12.5, margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
      <li>El título siempre va en Castellano (o como se haya publicado oficialmente en España).</li>
      <li>El proveedor nunca es obligatorio en WEB-DL — si no se sabe, se omite en vez de arriesgarse a poner uno incorrecto.</li>
      <li>Los paréntesis y corchetes <code>( ) [ ] {'{'} {'}'}</code> se eliminan del nombre del archivo y del título interno del .mkv (el título del aporte/torrent sí los conserva).</li>
      <li>No se usan caracteres que den problemas en el sistema de archivos: <code>: / ? *</code>, etc. — se sustituyen espacios por puntos en el nombre del fichero.</li>
      <li>El grupo/uploader (lo que va tras el último guion) no afecta a si el resto del nombre es correcto o no.</li>
    </ul>
  )
}

// --- Condiciones de subida ---------------------------------------------------

// Kept as data (not hand-written JSX rows) so the verdict column can be
// rendered consistently and a row can't accidentally ship without one.
type Verdict = 'ok' | 'blocked' | 'warn'

const VERDICT_LABEL: Record<Verdict, string> = {
  ok: 'Válida',
  blocked: 'Bloqueada',
  warn: 'No bloquea',
}

// Same three colours and the same icon the pre-upload checks use
// (CheckStatusIcon), so a verdict here reads exactly like the check the user
// will meet when they actually press Subir.
const VERDICT_COLOR: Record<Verdict, string> = {
  ok: '#22c55e',
  blocked: '#ef4444',
  warn: '#f59e0b',
}

const VERDICT_ICON: Record<Verdict, 'ok' | 'fail' | 'skip'> = {
  ok: 'ok',
  blocked: 'fail',
  warn: 'skip',
}

interface SpanishRow {
  kind: string
  audio: string
  subs: string
  verdict: Verdict
  verdictLabel?: string
  why: React.ReactNode
}

const SPANISH_ROWS: SpanishRow[] = [
  {
    kind: 'Temporada', audio: 'spa en todos', subs: 'ninguno', verdict: 'ok',
    why: 'Está doblada, así que el audio ya cumple la condición él solo. Una temporada doblada no necesita ninguna pista de subtítulos, ni siquiera una.',
  },
  {
    kind: 'Temporada', audio: 'eng en todos', subs: 'cap. 1-4 spa / eng, cap. 5-8 spa', verdict: 'ok',
    why: 'Como no está doblada, cada capítulo tiene que traer castellano en sus subtítulos, y los ocho lo traen. Que unos lleven además inglés y otros no da igual: los subtítulos no tienen que ser iguales entre capítulos.',
  },
  {
    kind: 'Temporada', audio: 'eng en todos', subs: 'todos spa salvo el cap. 6, con eng', verdict: 'blocked',
    why: (
      <>
        El capítulo 6 no está doblado y tampoco trae subtítulos en castellano, así que incumple él
        solo y tumba el pack entero. El aviso lo señala por número:{' '}
        <em>«El capítulo 6 no tiene castellano ni en el audio (eng) ni en los subtítulos (eng)»</em>.
        Arreglando ese capítulo, la temporada pasa.
      </>
    ),
  },
  {
    kind: 'Temporada', audio: 'cap. 1 spa, cap. 2 eng', subs: 'todos spa', verdict: 'ok',
    why: (
      <>
        Todos los capítulos tienen castellano, uno doblado y otro subtitulado, y eso basta. Que los
        audios no coincidan ya <strong>no bloquea</strong>: los idiomas se suman en el nombre del
        pack (<code>DUAL</code> aquí), porque el pack contiene los dos y anunciarlos los dos es
        exacto.
      </>
    ),
  },
  {
    kind: 'Capítulo suelto', audio: 'eng', subs: 'spa', verdict: 'ok', verdictLabel: 'Válido',
    why: 'No está doblado, pero trae subtítulos en castellano, que es exactamente la alternativa que acepta el tracker.',
  },
  {
    kind: 'Capítulo suelto', audio: 'es-419', subs: 'sin detectar', verdict: 'blocked',
    verdictLabel: 'Bloqueado',
    why: (
      <>
        El audio es latino, que no cuenta como castellano, así que todo depende de los subtítulos. Y
        ahí no hay dato: puede ser que el archivo <strong>no tenga</strong> pistas de subtítulos, o
        que <strong>las tenga dañadas</strong> y MediaInfo no consiga leerlas, en cuyo caso el
        archivo necesitaría una reparación (remux). Sin ese dato no se puede afirmar que cumpla,
        aunque podría estar cumpliendo.
      </>
    ),
  },
  {
    kind: 'Película', audio: 'spa / eng', subs: 'ninguno', verdict: 'ok',
    why: 'Trae pista de audio en castellano, aunque también traiga inglés. Con que exista una basta, y entonces los subtítulos no se piden.',
  },
  {
    kind: 'Película', audio: 'eng', subs: 'eng', verdict: 'blocked',
    why: 'Ni doblada ni subtitulada al castellano: no cumple por ninguna de las dos vías. Necesita que le añadas una pista de subtítulos en castellano, o una de audio.',
  },
  {
    kind: 'Película o capítulo', audio: 'sin detectar', subs: 'cualquiera', verdict: 'blocked',
    verdictLabel: 'Bloqueado',
    why: (
      <>
        Que no se detecte el audio es raro y casi siempre apunta a un problema del archivo:
        prácticamente todo vídeo trae al menos una pista de audio, así que si no aparece suele ser
        porque <strong>las pistas están dañadas</strong> o el contenedor está mal formado y MediaInfo
        no puede leerlo. Ese archivo necesita reparación (un remux) antes de subirse. También puede
        ocurrir que simplemente nunca se haya leído su MediaInfo todavía: en ese caso se resuelve
        leyéndolo desde la propia ficha.
      </>
    ),
  },
]

interface OtherRow {
  applies: string
  condition: string
  verdict: Verdict
  verdictLabel?: string
  why: string
}

const OTHER_CONDITION_ROWS: OtherRow[] = [
  {
    applies: 'Pack de temporada', condition: 'Falta algún capítulo por descargar',
    verdict: 'blocked', verdictLabel: 'Bloquea',
    why: 'Un pack de temporada es un único release que contiene la temporada completa. Con huecos, quien se lo descargue no recibe lo que el nombre promete.',
  },
  {
    applies: 'Pack de temporada', condition: 'Los capítulos están en carpetas distintas',
    verdict: 'blocked', verdictLabel: 'Bloquea',
    why: 'El pack se arma sobre la carpeta que los capítulos ya comparten, renombrándolos ahí mismo. No se mueven archivos de sitio, así que si están repartidos no hay carpeta que usar. Muévelos a una común.',
  },
  {
    applies: 'Pack de temporada',
    condition: 'Los capítulos no coinciden en resolución o en códec de vídeo',
    verdict: 'blocked', verdictLabel: 'Bloquea',
    why: 'Son los dos únicos que tienen que coincidir. Una temporada con capítulos a 1080p y a 720p no es una calidad, son dos, y el nombre solo puede declarar una; con el códec de vídeo pasa lo mismo.',
  },
  {
    applies: 'Pack de temporada',
    condition: 'Los capítulos no coinciden en source, códec de audio, idiomas de audio o subtítulos',
    verdict: 'warn', verdictLabel: 'No bloquea',
    why: 'Se resuelve en el nombre en vez de rechazar el pack: los audios se suman (ver «El audio de un pack: cuándo aparece CUSTOM») y el source que no coincida se deja fuera del nombre, porque declarar uno solo sería mentir sobre el resto de capítulos.',
  },
  {
    applies: 'Cualquiera', condition: 'El contenido está Faltante',
    verdict: 'blocked', verdictLabel: 'Ni se puede intentar',
    why: 'El botón Subir aparece deshabilitado: no tienes el archivo en disco, así que no hay nada que subir.',
  },
  {
    applies: 'Cualquiera', condition: 'La carpeta del archivo no permite escritura',
    verdict: 'blocked', verdictLabel: 'Bloquea',
    why: 'La subida renombra el archivo a la nomenclatura de eMuwarez en su sitio, sin copiarlo. Sin permiso de escritura en su carpeta, ese renombrado no se puede hacer.',
  },
  {
    applies: 'Cualquiera', condition: 'El directorio de salida de Uploadrr no permite escritura',
    verdict: 'blocked', verdictLabel: 'Bloquea',
    why: 'Es donde se generan el .torrent, las capturas y la descripción antes de enviarlos. Sin poder escribir ahí no hay nada que subir.',
  },
  {
    applies: 'Cualquiera', condition: 'eMuwarez no responde',
    verdict: 'blocked', verdictLabel: 'Bloquea',
    why: 'Es el destino de la subida. Suele ser la API key mal puesta o el tracker caído.',
  },
  {
    applies: 'Cualquiera', condition: 'El repositorio de imágenes no responde',
    verdict: 'blocked', verdictLabel: 'Bloquea',
    why: 'Las capturas son obligatorias en la publicación, y se suben a ese repositorio antes de crear el torrent.',
  },
  {
    applies: 'Cualquiera', condition: 'qBittorrent sin configurar',
    verdict: 'warn', verdictLabel: 'No bloquea',
    why: 'La subida se completa igual. Lo único que pierdes es que el .torrent se añada solo a la cola al terminar; tendrías que añadirlo a mano para sembrar.',
  },
]

function VerdictCell({ verdict, label }: { verdict: Verdict; label?: string }) {
  return (
    <span style={{
      color: VERDICT_COLOR[verdict], fontWeight: 600, whiteSpace: 'nowrap',
      display: 'inline-flex', alignItems: 'center', gap: 6,
    }}>
      <CheckStatusIcon status={VERDICT_ICON[verdict]} />
      {label ?? VERDICT_LABEL[verdict]}
    </span>
  )
}

function UploadConditionsContent() {
  return (
    <>
      <h4 style={{ fontSize: 13, margin: '0 0 6px' }}>Castellano</h4>
      <p style={{ fontSize: 12.5, marginTop: 0 }}>
        eMuwarez exige castellano, pero no importa por dónde venga. Si el audio está en castellano,
        la condición ya se cumple y los subtítulos no se piden. Si el audio no está en castellano,
        entonces hacen falta subtítulos en castellano. El latino (<code>es-419</code>) es un idioma
        distinto y no vale como castellano.
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table" style={{ fontSize: 12.5 }}>
          <thead>
            <tr>
              <th>Tipo</th><th>Audio</th><th>Subtítulos</th><th>Resultado</th><th>Por qué</th>
            </tr>
          </thead>
          <tbody>
            {SPANISH_ROWS.map((r, i) => (
              <tr key={i}>
                <td style={{ whiteSpace: 'nowrap' }}>{r.kind}</td>
                <td style={{ fontFamily: 'monospace' }}>{r.audio}</td>
                <td style={{ fontFamily: 'monospace' }}>{r.subs}</td>
                <td><VerdictCell verdict={r.verdict} label={r.verdictLabel} /></td>
                <td>{r.why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: 12.5 }}>
        <strong>Cuando no hay datos, se bloquea.</strong> Un archivo cuyas pistas no se han podido
        leer no se puede dar por bueno: «no lo hemos mirado» o «no se ha podido leer» no es prueba de
        que cumpla. Si el dato falta de forma persistente después de leer el MediaInfo, sospecha del
        archivo, no de la comprobación. Esto no afecta al contenido doblado, porque a ese le basta
        con el audio.
      </p>

      <h4 style={{ fontSize: 13, margin: '18px 0 6px' }}>Otras condiciones que bloquean</h4>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table" style={{ fontSize: 12.5 }}>
          <thead>
            <tr><th>Aplica a</th><th>Condición</th><th>Resultado</th><th>Por qué</th></tr>
          </thead>
          <tbody>
            {OTHER_CONDITION_ROWS.map((r, i) => (
              <tr key={i}>
                <td style={{ whiteSpace: 'nowrap' }}>{r.applies}</td>
                <td>{r.condition}</td>
                <td><VerdictCell verdict={r.verdict} label={r.verdictLabel} /></td>
                <td>{r.why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h4 style={{ fontSize: 13, margin: '18px 0 6px' }}>El audio de un pack: cuándo aparece CUSTOM</h4>
      <p style={{ fontSize: 12.5, marginTop: 0 }}>
        El nombre de un pack solo puede anunciar una pista que <strong>tengan todos los
        capítulos</strong>. Esa es toda la regla, y de ahí sale el resto:
      </p>
      <ul style={{ fontSize: 12.5, marginTop: 0, paddingLeft: 18 }}>
        <li>
          Un idioma que en todos los capítulos viene con la misma pista se anuncia tal cual.
          Si dentro de cada capítulo ese idioma trae además una pista peor, se nombra la mejor:
          no es mentira, todos la tienen.
        </li>
        <li>
          Un idioma cuya pista <strong>cambia</strong> de un capítulo a otro no se puede resumir en
          una sola. Anunciar la mejor mentiría sobre los capítulos que solo traen la peor, así que
          se listan <strong>todas sus variantes</strong> y el nombre se marca <code>CUSTOM</code>.
        </li>
        <li>
          Un idioma que solo está en <strong>algunos</strong> capítulos es el mismo caso: falta en
          los demás, así que también marca <code>CUSTOM</code>.
        </li>
      </ul>
      <p style={{ fontSize: 12.5 }}>
        Los canales cuentan como parte de la pista: 5.1 en unos capítulos y 2.0 en otros ya es
        CUSTOM, porque quien se baje el pack no recibe 5.1 en todos. Y <code>CUSTOM</code> es
        <strong> solo por el audio</strong>: un source o un proveedor mezclados no lo activan, esos
        simplemente se caen del nombre. Va justo antes del proveedor
        (<code>… 1080p CUSTOM BluRay x264 …</code>), como en el resto del catálogo de eMuwarez.
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table" style={{ fontSize: 12.5 }}>
          <thead>
            <tr><th>Los capítulos traen</th><th>El pack se llama</th><th>Por qué</th></tr>
          </thead>
          <tbody>
            {([
              ['Todos: ING TrueHD Atmos 7.1 + ESP DD+ 5.1',
               'ING TrueHD Atmos 7.1 ESP DD+ 5.1',
               'Nadie se queda fuera: las dos pistas están en los diez capítulos.'],
              ['5 con ING DD+ Atmos 5.1 y 5 con ING DD+ 5.1 (ESP y JAP iguales)',
               'CUSTOM … ING DD+ Atmos 5.1 ING-ESP-JAP DD+ 5.1',
               'El Atmos solo está en la mitad. Se anuncian las dos versiones del inglés y CUSTOM avisa de que no todos los capítulos son iguales.'],
              ['Todos con ESP, el JAP solo en 4 capítulos',
               'CUSTOM … ESP DD+ 5.1 JAP FLAC 2.0',
               'El japonés se anuncia porque está, y CUSTOM avisa de que no está en todos.'],
              ['ESP DD+ 5.1 en unos, ESP DD+ 2.0 en otros',
               'CUSTOM … ESP-ING DD+ 5.1 ESP DD+ 2.0',
               'Mismo códec, distintos canales: sigue siendo otra pista.'],
              ['Todos: ESP DD 5.1 + ING DD 5.1',
               'DUAL DD 5.1',
               'Sin CUSTOM, DUAL y MULTI siguen valiendo: ahí sí es verdad que todos los capítulos traen esos idiomas.'],
            ] as [string, string, string][]).map(([tienen, nombre, why], i) => (
              <tr key={i}>
                <td>{tienen}</td>
                <td style={{ fontFamily: 'monospace' }}>{nombre}</td>
                <td>{why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: 12.5 }}>
        Ojo con la última fila: <code>DUAL</code> y <code>MULTI</code> son atajos que prometen que
        el release trae esos idiomas. En un pack CUSTOM un mismo idioma puede salir en dos sitios,
        así que ahí no se usan — los idiomas se escriben uno a uno.
      </p>

      <h4 style={{ fontSize: 13, margin: '18px 0 6px' }}>Una temporada con datos mezclados</h4>
      <p style={{ fontSize: 12.5, marginTop: 0 }}>
        Como el source, el códec de audio y los idiomas ya no tienen que coincidir, una temporada
        puede tener <strong>varios valores</strong> en esos campos. La ficha te los enseña todos
        (<code>WEB-DL, BluRay</code>) en vez de dejarlos en blanco. Pero al cruzarla con una
        petición, un campo mezclado se comporta como <strong>«no lo sé»</strong>: no puede
        prometerse. Solo deja de importar si la petición no restringe ese campo.
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table" style={{ fontSize: 12.5 }}>
          <thead>
            <tr><th>La petición pide</th><th>Tu temporada tiene</th><th>Resultado</th><th>Por qué</th></tr>
          </thead>
          <tbody>
            {([
              ['1080p · WEB-DL', '1080p · WEB-DL en todos', 'ok', 'Coincidencia perfecta.'],
              ['1080p · cualquier source', '1080p · WEB-DL, BluRay', 'ok', 'La petición no restringe el source, así que la mezcla da igual.'],
              ['1080p · WEB-DL', '1080p · WEB-DL, BluRay', 'warn', 'No puedes prometer WEB-DL: la mitad de los capítulos no lo son.'],
              ['720p · cualquier source', '1080p en todos', 'ok', 'La comparación es «iguala o mejora», y 1080p supera lo pedido.'],
              ['1080p · WEB-DL', '1080p, 720p mezclado', 'warn', 'No puedes prometer una resolución que no tienen todos. Y además esa temporada no se puede subir como pack.'],
              ['Sin resolución · cualquier source', '1080p, 720p mezclado', 'warn', 'La comparación no tiene nada que exigir, pero el pack sigue bloqueado por la resolución, así que no sale Compatible: sus capítulos sí se pueden subir uno a uno.'],
              ['2160p · BluRay', '1080p · WEB-DL', 'blocked', 'Fallan los dos campos.'],
            ] as [string, string, Verdict, string][]).map(([pide, tengo, verdict, why], i) => (
              <tr key={i}>
                <td style={{ fontFamily: 'monospace' }}>{pide}</td>
                <td style={{ fontFamily: 'monospace' }}>{tengo}</td>
                <td><VerdictCell verdict={verdict} label={verdict === 'ok' ? 'Compatible' : verdict === 'warn' ? 'Parcial' : 'No compatible'} /></td>
                <td>{why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: 12.5 }}>
        <strong>Ojo con la penúltima fila.</strong> Si la petición no pide resolución, la comparación
        no tiene nada que exigir y saldría Compatible aunque la temporada esté descuadrada. Como ese
        pack no se puede armar, se baja a Parcial y se explica el motivo: prometer algo que la subida
        va a rechazar es peor que no prometerlo.
      </p>
    </>
  )
}

interface GuideSection {
  id: string
  label: string
  title: string
  render: () => React.ReactNode
}

const SECTIONS: GuideSection[] = [
  { id: 'formula', label: 'Fórmula del nombre', title: 'Fórmula del nombre', render: FormulaContent },
  { id: 'fields', label: 'Campos y de dónde los obtiene la aplicación', title: 'Campos y de dónde los obtiene la aplicación', render: FieldSourcesContent },
  { id: 'tech', label: 'Especificaciones técnicas (MediaInfo → Nombre)', title: 'Especificaciones técnicas (MediaInfo → Nombre)', render: TechSpecsContent },
  { id: 'examples', label: 'Ejemplos completos', title: 'Ejemplos completos', render: ExamplesContent },
  { id: 'rules', label: 'Reglas de nombrado de archivo', title: 'Reglas de nombrado de archivo', render: RulesContent },
  { id: 'upload', label: 'Condiciones de subida', title: 'Condiciones de subida', render: UploadConditionsContent },
]

export function GuidePage() {
  const [openId, setOpenId] = useState<string>('formula')
  const openSection = SECTIONS.find(s => s.id === openId) ?? SECTIONS[0]

  return (
    <div data-tour="guide-content" style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div className="page-header" style={{ flexShrink: 0 }}>
        <div>
          <div className="page-title">Guía</div>
          <p style={{ fontSize: 12.5, color: 'var(--text-muted)', margin: '4px 0 0' }}>
            Nomenclatura oficial de eMuwarez y de dónde obtiene la aplicación cada dato para construirla.
          </p>
        </div>
      </div>

      {/* One row, one column per section — click any to select it, marking
          that column as active and showing its content in the panel below
          (inline, not a modal). Fórmula del nombre is selected by default. */}
      <div className="detail-card" style={{ borderRadius: 10, overflowX: 'auto', marginTop: 20, flexShrink: 0 }}>
        <table className="data-table" style={{ tableLayout: 'fixed', width: '100%' }}>
          <tbody>
            <tr>
              {SECTIONS.map(s => {
                const active = s.id === openId
                return (
                  <td key={s.id} style={{ padding: 0, textAlign: 'center', verticalAlign: 'middle' }}>
                    <button
                      type="button"
                      onClick={() => setOpenId(s.id)}
                      className="btn btn-ghost"
                      style={{
                        width: '100%', height: '100%', minHeight: 64, borderRadius: 0,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        textAlign: 'center', fontSize: 13, fontWeight: active ? 700 : 600, lineHeight: 1.35,
                        padding: '12px 14px', whiteSpace: 'normal',
                        background: active ? 'var(--bg-card)' : undefined,
                        color: active ? 'var(--text-accent)' : undefined,
                        borderBottom: active ? '2px solid var(--text-accent)' : '2px solid transparent',
                      }}
                    >
                      {s.label}
                    </button>
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>
      </div>

      {/* Fills the remaining vertical space and scrolls internally — same
          fill+internal-scroll pattern as Biblioteca's Temporadas/Capítulos
          and Subidas' "Progreso de la subida", so long content (like the
          técnicas tables) never grows the page past the usual bottom margin. */}
      <div
        className="detail-card"
        style={{ borderRadius: 10, marginTop: 16, padding: '16px 18px', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
      >
        <h3 style={{ margin: '0 0 14px', fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', flexShrink: 0 }}>
          {openSection.title}
        </h3>
        <div style={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
          {openSection.render()}
        </div>
      </div>
    </div>
  )
}
