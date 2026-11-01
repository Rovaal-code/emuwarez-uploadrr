// «Chrome en Windows» a partir de un user-agent; si no se reconoce nada, el texto tal cual, recortado.
export function descripcionDeSesion(ua: string | null | undefined): string {
  if (!ua) return 'Navegador desconocido'
  const navegador = /Edg\//.test(ua) ? 'Edge'
    : /OPR\/|Opera/.test(ua) ? 'Opera'
    : /Firefox\//.test(ua) ? 'Firefox'
    : /Chrome\/|CriOS\//.test(ua) ? 'Chrome'
    : /Safari\//.test(ua) ? 'Safari'
    : null
  // Android antes que Linux, y iOS antes que macOS: sus user-agent llevan también esas palabras.
  const sistema = /Windows/.test(ua) ? 'Windows'
    : /Android/.test(ua) ? 'Android'
    : /iPhone|iPad|iPod/.test(ua) ? 'iOS'
    : /Mac OS X|Macintosh/.test(ua) ? 'macOS'
    : /Linux|X11/.test(ua) ? 'Linux'
    : null
  if (!navegador && !sistema) return ua.slice(0, 60)
  return `${navegador ?? 'Navegador'}${sistema ? ` en ${sistema}` : ''}`
}
