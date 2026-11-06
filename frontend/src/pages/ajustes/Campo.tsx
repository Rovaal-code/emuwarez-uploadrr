import { useId, type ReactNode } from 'react'
import type { IntegrationTestResult } from '../../api/integrationTests'
import { testResultLabel } from '../../utils/integrationResult'
import { IconoAviso } from '../../components/Iconos'

// Lo que el control de dentro tiene que llevar para quedar ligado a su etiqueta, su ayuda y su error.
export interface PropsDeControl {
  id: string
  'aria-describedby'?: string
  'aria-invalid'?: true
}

// Una etiqueta ligada a su control (clic en la etiqueta y lectores de pantalla), con la nota entre paréntesis,
// la ayuda debajo y el error en rojo. El control se pinta con una función para recibir su id y sus aria-*.
export function Campo({ id, etiqueta, nota, info, ayuda, error, className, children }: {
  // Un id fijo, para quien necesita enlazar al control (una prueba, un ancla); si no, se genera.
  id?: string
  etiqueta: ReactNode
  nota?: string
  info?: ReactNode
  ayuda?: ReactNode
  error?: string | null
  className?: string
  children: (control: PropsDeControl) => ReactNode
}) {
  const automatico = useId()
  const base = id ?? automatico
  const idAyuda = ayuda ? `${base}-ayuda` : undefined
  const idError = error ? `${base}-error` : undefined
  const describedby = [idError, idAyuda].filter(Boolean).join(' ') || undefined
  return (
    <div className={`form-group aj-campo${className ? ` ${className}` : ''}`}>
      <label className="form-label aj-campo__etiqueta" htmlFor={base}>
        {etiqueta}
        {nota && <>{' '}<span className="form-hint">({nota})</span></>}
        {info}
      </label>
      {children({ id: base, 'aria-describedby': describedby, 'aria-invalid': error ? true : undefined })}
      {error && <span id={idError} className="form-error aj-campo__error" role="alert">{error}</span>}
      {ayuda && <span id={idAyuda} className="form-hint">{ayuda}</span>}
    </div>
  )
}

// Un ajuste de sí o no: la etiqueta (con su «?») a la izquierda y el interruptor a la derecha. Es un checkbox con
// role="switch", así que el teclado y los lectores de pantalla lo tratan como un interruptor.
export function Interruptor({ etiqueta, info, marcado, onCambio, className }: {
  etiqueta: ReactNode
  info?: ReactNode
  marcado: boolean
  onCambio: (marcado: boolean) => void
  className?: string
}) {
  const id = useId()
  return (
    <div className={`form-group aj-interruptor${className ? ` ${className}` : ''}`}>
      <label className="form-label aj-interruptor__etiqueta" htmlFor={id}>{etiqueta}{info}</label>
      <input
        id={id}
        type="checkbox"
        role="switch"
        className="aj-interruptor__control"
        checked={marcado}
        onChange={e => onCambio(e.target.checked)}
      />
    </div>
  )
}

// Una clave o un secreto guardado: dice si hay uno sin enseñarlo (la parte enmascarada que da el servidor basta para reconocerlo).
export function EstadoSecreto({ configurado, enmascarado, genero = 'f' }: {
  configurado: boolean | undefined
  enmascarado?: string | null
  genero?: 'f' | 'm'
}) {
  const si = genero === 'f' ? 'Configurada' : 'Configurado'
  return (
    <span className="aj-estado-secreto">
      <span className={`aj-estado aj-estado--${configurado ? 'ok' : 'falta'}`}>
        <span className="aj-estado__punto" aria-hidden />
        {configurado ? si : 'Sin configurar'}
      </span>
      {configurado && enmascarado && <code className="aj-code-mascara">{enmascarado}</code>}
    </span>
  )
}

// El resultado de un «Probar conexión»: texto de siempre (con su icono) y un color por tono, no solo por color.
export function ResultadoPrueba({ resultado }: { resultado: IntegrationTestResult | null }) {
  if (!resultado) return null
  const tono = resultado.ok ? 'ok' : resultado.status === 'not_configured' ? 'aviso' : 'error'
  const texto = testResultLabel(resultado)
  // El aviso lleva el icono del sistema en vez del glifo ⚠, que se pinta con el grosor de la fuente.
  return (
    <span role="status" className={`aj-resultado aj-resultado--${tono}`}>
      {texto.startsWith('⚠ ') ? <><IconoAviso /> {texto.slice(2)}</> : texto}
    </span>
  )
}

// Tras un intento de guardar con errores, el foco va al primer campo inválido de `raiz` (cuando React ya lo ha marcado).
export function enfocarPrimerError(raiz: string) {
  requestAnimationFrame(() => {
    const campo = document.querySelector<HTMLElement>(`${raiz} [aria-invalid="true"]`)
    campo?.focus()
    campo?.scrollIntoView?.({ block: 'center', behavior: 'auto' })
  })
}
