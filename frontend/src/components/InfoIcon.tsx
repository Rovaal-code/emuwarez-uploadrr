import { Tooltip } from './Tooltip'

// Small "?" info badge next to a field label. Hovering shows an app-styled
// tooltip (not the native browser box) explaining where the field comes from.
export function InfoIcon({ text, size = 13 }: { text: React.ReactNode; size?: number }) {
  return (
    <Tooltip content={text}>
      <span
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: size, height: size, borderRadius: '50%', border: '1px solid var(--text-muted)',
          fontSize: size - 4, cursor: 'help', flexShrink: 0, color: 'var(--text-muted)',
        }}
      >
        ?
      </span>
    </Tooltip>
  )
}
