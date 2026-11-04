/**
 * Un lote: varias subidas encoladas juntas (las tandas del asistente, y más adelante «Subir por lotes»). Comparten
 * un `lote_id` que genera el navegador, y Subidas las agrupa y filtra por él.
 */

// Copia de services/lotes.py::MAX_ELEMENTOS_LOTE: test_copias_frontend.py vigila que coincidan.
export const MAX_ELEMENTOS_LOTE = 50

// Lo único que acepta el servidor como `lote_id`: 12 caracteres hexadecimales en minúscula.
export const PATRON_LOTE_ID = /^[0-9a-f]{12}$/

const BYTES_LOTE_ID = 6

/** Un `lote_id` nuevo (12 hex). Sin `crypto.getRandomValues` (un navegador muy viejo o un test), con Math.random. */
export function nuevoLoteId(): string {
  const bytes = new Uint8Array(BYTES_LOTE_ID)
  const cripto = (globalThis as { crypto?: Crypto }).crypto
  if (cripto && typeof cripto.getRandomValues === 'function') {
    cripto.getRandomValues(bytes)
  } else {
    for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256)
  }
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
}
