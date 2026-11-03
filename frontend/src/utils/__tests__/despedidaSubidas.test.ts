/**
 * Qué subidas acaban de terminar, para que no se esfumen del Panel de golpe.
 *
 * Lo delicado es que "terminada" no se detecta mirando el estado sino el PASO
 * de viva a no viva. Mirando el estado, una subida ya terminada volvería a
 * "acabar de terminar" en cada vuelta del sondeo y se quedaría en pantalla
 * para siempre, reiniciando su cuenta atrás una y otra vez.
 */
import { describe, it, expect } from 'vitest'
import { queSalieron, soloVivas, idsDe, ESPERA_MS, DESVANECER_MS } from '../despedidaSubidas'
import type { UploadJob } from '../../types/api'

const job = (id: number, status: string) => ({ id, status, title: `Job ${id}` } as UploadJob)

describe('cuáles acaban de terminar', () => {
  it('la que estaba viva y ya no lo está', () => {
    const salieron = queSalieron([job(1, 'completed')], new Set([1]))
    expect(salieron.map(j => j.id)).toEqual([1])
  })

  it('la que sigue viva no sale', () => {
    expect(queSalieron([job(1, 'running')], new Set([1]))).toEqual([])
  })

  // El fallo importa MÁS que el éxito: es lo que no llegarías a ver nunca
  // desde el Panel si la fila se esfumara en el acto.
  it.each(['completed', 'failed', 'cancelled'])('cualquier final cuenta: %s', estado => {
    expect(queSalieron([job(1, estado)], new Set([1])).map(j => j.id)).toEqual([1])
  })

  // Esta es la que evita que se quede clavada: en la vuelta siguiente ya no
  // estaba viva antes, así que no vuelve a "terminar".
  it('no vuelve a terminar en la siguiente vuelta', () => {
    const todas = [job(1, 'completed')]
    const primera = queSalieron(todas, new Set([1]))
    expect(primera).toHaveLength(1)
    const segunda = queSalieron(todas, idsDe(soloVivas(todas)))
    expect(segunda).toEqual([])
  })

  it('una que nunca estuvo viva para esta pantalla no cuenta', () => {
    // Terminó mientras mirabas otra sección: no te has perdido nada al volver.
    expect(queSalieron([job(9, 'completed')], new Set())).toEqual([])
  })

  it('con varias a la vez, solo salen las que salieron', () => {
    const todas = [job(1, 'completed'), job(2, 'running'), job(3, 'failed')]
    expect(queSalieron(todas, new Set([1, 2, 3])).map(j => j.id)).toEqual([1, 3])
  })

  it('una subida sin id no rompe nada', () => {
    const sinId = { status: 'completed', title: 'x' } as UploadJob
    expect(queSalieron([sinId], new Set([1]))).toEqual([])
    expect(idsDe([sinId]).size).toBe(0)
  })
})

describe('cuáles están vivas', () => {
  it.each(['queued', 'staging', 'preparing', 'running'])('%s está viva', estado => {
    expect(soloVivas([job(1, estado)])).toHaveLength(1)
  })

  it.each(['completed', 'failed', 'cancelled'])('%s no', estado => {
    expect(soloVivas([job(1, estado)])).toEqual([])
  })
})

describe('los tiempos', () => {
  it('se queda diez segundos quieta antes de irse', () => {
    expect(ESPERA_MS).toBe(10_000)
  })

  // Que se desvanezca tiene que verse como un desvanecimiento, no como un
  // parpadeo: por debajo de medio segundo se lee igual que desaparecer.
  it('el desvanecimiento dura lo suficiente para notarse', () => {
    expect(DESVANECER_MS).toBeGreaterThanOrEqual(500)
    expect(DESVANECER_MS).toBeLessThan(ESPERA_MS)
  })
})
