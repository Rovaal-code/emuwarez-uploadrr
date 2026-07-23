// Reference page synthesizing eMuwarez's official nomenclature spec and
// upload guidelines, PLUS — for each field — exactly where THIS APP gets
// that value from (Radarr/Sonarr, TMDb, the real file via MediaInfo,
// filename inference, or a Settings value), so a user can understand why a
// generated name looks the way it does. Purely informational, no state
// beyond which section's modal is currently open.

import { useState } from 'react'

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
    example: '2160p UHD',
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
  ['Full Ultra HD 8k', '4320p FUHD'],
  ['Ultra HD 4k', '2160p UHD'],
  ['Full HD', '1080p'],
  ['HD', '720p'],
  ['SD', '576p SD'],
  ['SD', '540p SD'],
  ['SD', '480p SD'],
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
  'Brave - Indomable 2012 2160p UHD AV1 MULTI DD 5.1 SUBS - EMUWAREZ',
  'La trama fenicia 2025 2160p UHD MA WEB-DL DV HDR HEVC ESP DD+ 5.1 ING DD+ Atmos 5.1 SUBS-EMUWAREZ',
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
