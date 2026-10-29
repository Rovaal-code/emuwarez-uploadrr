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
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: size, height: size, borderRadius: '50%', border: '1px solid var(--text-muted)',
          fontSize: size - 4, cursor: 'help', flexShrink: 0, color: 'var(--text-muted)',
          background: 'transparent', padding: 0, lineHeight: 1,
        }}
      >
        ?
      </button>
    </Tooltip>
  )
}
