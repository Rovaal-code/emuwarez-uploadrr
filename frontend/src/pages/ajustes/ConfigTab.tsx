import type { SaveExpose } from './tipos'
import { ErrorDeCarga } from './ErrorDeCarga'
import { useConfigForm } from './config/useConfigForm'
import { AccountCard } from './config/AccountCard'
import { SessionsCard } from './config/SessionsCard'
import { WidgetCard } from './config/WidgetCard'
import { EmuwarezCard } from './config/EmuwarezCard'
import { TmdbCard } from './config/TmdbCard'
import { QbitCard } from './config/QbitCard'
import { ProveedoresVideoCard } from './config/ProveedoresVideoCard'
import { ProveedoresImagenesCard } from './config/ProveedoresImagenesCard'
import { BibliotecaCard } from './config/BibliotecaCard'
import { OtrosCard } from './config/OtrosCard'

export function ConfigTab({ onExposeSave }: { onExposeSave: (a: SaveExpose | null) => void }) {
  const form = useConfigForm(onExposeSave)

  if (form.loading) return <p className="aj-cargando">Cargando…</p>
  if (form.errorCarga) {
    return (
      <div className="aj-cargando">
        <ErrorDeCarga mensaje={`No se pudo cargar la configuración: ${form.errorCarga}`} onReintentar={form.reintentar} />
      </div>
    )
  }

  return (
    <div data-tour="settings-content" className="aj-col-16">
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
      <WidgetCard />
      </div>
    </div>
  )
}
