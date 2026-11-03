import { Tooltip } from './Tooltip'

// Small "?" info badge next to a field label. Hovering shows an app-styled
// tooltip (not the native browser box) explaining where the field comes from.
// Es un <button> para que la explicación también llegue con el teclado: Tab
// lo enfoca y el tooltip se abre al momento.
export function InfoIcon({ text, size = 13 }: { text: React.ReactNode; size?: number }) {
  return (
    <Tooltip content={text}>
      <button
        type="button"
        aria-label="Más información"
        className="menores-info"
        style={{ width: size, height: size, fontSize: size - 4 }}
      >
        ?
      </button>
    </Tooltip>
  )
}
