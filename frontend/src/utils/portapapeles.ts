/** Copia `texto` al portapapeles. `navigator.clipboard` solo existe en contextos seguros (https o localhost) y la
 *  app suele servirse por http en la red local: ahí se cae a `execCommand('copy')`. Devuelve si llegó a copiar. */
export async function copiarTexto(texto: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(texto)
      return true
    }
  } catch { /* sin permiso o sin foco: se prueba el otro camino */ }
  const area = document.createElement('textarea')
  area.value = texto
  area.setAttribute('readonly', '')
  area.className = 'portapapeles-oculto'
  const enfocado = document.activeElement instanceof HTMLElement ? document.activeElement : null
  document.body.appendChild(area)
  try {
    area.select()
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    area.remove()
    enfocado?.focus()
  }
}
