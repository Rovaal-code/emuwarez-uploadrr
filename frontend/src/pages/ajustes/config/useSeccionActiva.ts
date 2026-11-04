import { useEffect, useRef, useState, type RefObject } from 'react'

// La sección activa del índice: la primera, en el orden del índice, que cruza la franja alta de la ventana, o la
// última en cuanto se ve entera. Una sección elegida con un clic manda mientras siga a la vista, para que el
// observador no la cambie a mitad del desplazamiento.
export function useSeccionActiva(ids: readonly string[], contenedor: RefObject<HTMLElement | null>) {
  const [activa, setActiva] = useState(ids[0])
  const elegida = useRef<string | null>(null)

  useEffect(() => {
    const raiz = contenedor.current
    if (!raiz || typeof IntersectionObserver === 'undefined') return
    const visibles = new Set<string>()
    let ultimaEntera = false
    const elegirActiva = () => {
      const propia = elegida.current
      const siguiente = propia && visibles.has(propia) ? propia
        : ultimaEntera ? ids[ids.length - 1] : ids.find(id => visibles.has(id))
      if (siguiente) setActiva(siguiente)
    }
    const franja = new IntersectionObserver(entradas => {
      for (const e of entradas) {
        const id = (e.target as HTMLElement).dataset.seccion
        if (!id) continue
        if (e.isIntersecting) visibles.add(id)
        else visibles.delete(id)
      }
      elegirActiva()
    }, { rootMargin: '0px 0px -55% 0px' })
    const final = new IntersectionObserver(entradas => {
      ultimaEntera = entradas.some(e => e.intersectionRatio >= 0.99)
      elegirActiva()
    }, { threshold: [0, 0.99] })
    raiz.querySelectorAll('[data-seccion]').forEach(el => franja.observe(el))
    const ultima = raiz.querySelector(`[data-seccion="${ids[ids.length - 1]}"]`)
    if (ultima) final.observe(ultima)
    return () => { franja.disconnect(); final.disconnect() }
  }, [ids, contenedor])

  function elegir(id: string) {
    elegida.current = id
    setActiva(id)
  }
  return { activa, elegir }
}
