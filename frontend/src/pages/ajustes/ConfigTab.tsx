import type { SaveExpose } from './tipos'
import { useConfigForm } from './config/useConfigForm'
import { AccountCard } from './config/AccountCard'
import { SessionsCard } from './config/SessionsCard'
import { EmuwarezCard } from './config/EmuwarezCard'
import { TmdbCard } from './config/TmdbCard'
import { QbitCard } from './config/QbitCard'
import { ProveedoresVideoCard } from './config/ProveedoresVideoCard'
import { ProveedoresImagenesCard } from './config/ProveedoresImagenesCard'
import { BibliotecaCard } from './config/BibliotecaCard'
import { OtrosCard } from './config/OtrosCard'

export function ConfigTab({ onExposeSave }: { onExposeSave: (a: SaveExpose | null) => void }) {
  const form = useConfigForm(onExposeSave)

  if (form.loading) return <p style={{ padding: 20, color: 'var(--text-muted)', fontSize: 13 }}>Cargando…</p>

  return (
    <div data-tour="settings-content" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Ocho tarjetas en cuatro columnas de ancho: cada una con el alto que
          le pida su contenido (ver settings-config-grid en dashboard.css). La
          página entera se desplaza si no caben todas, no cada tarjeta por
          separado. */}
      <div className="settings-config-grid">
      <AccountCard />
      <SessionsCard />
      <EmuwarezCard form={form} />
      <TmdbCard form={form} />
      <QbitCard form={form} />
      <ProveedoresVideoCard form={form} />
      <ProveedoresImagenesCard form={form} />
      <BibliotecaCard form={form} />
      <OtrosCard form={form} />
      </div>
    </div>
  )
}
