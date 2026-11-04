// @vitest-environment jsdom
/**
 * Peticiones con el servidor simulado: los grupos por lo que se puede hacer, su orden por recompensa, que una
 * ordenación elegida los quite.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/requests', () => ({ getRequests: vi.fn(), getRequestDetail: vi.fn() }))
vi.mock('../../api/requestReadiness', () => ({ getCandidates: vi.fn(), getReadiness: vi.fn() }))
vi.mock('../../api/library', () => ({ getLibraryItem: vi.fn() }))
vi.mock('../../api/instances', () => ({ getInstances: vi.fn() }))
vi.mock('../../components/UploadWizardModal', () => ({ UploadWizardModal: () => null }))

import { getRequests } from '../../api/requests'
import { getInstances } from '../../api/instances'
import { SeccionVisible } from '../../context/SeccionVisible'
import { SyncContext } from '../../context/SyncContext'
import type { RequestItemResponse } from '../../types/api'
import { desmontar, elegir, esperar, montar, pulsar } from '../../components/__tests__/dom'
import { RequestsPage } from '../RequestsPage'

const peticion = (id: number, extra: Partial<RequestItemResponse>): RequestItemResponse => ({
  id, emu_id: String(id), title: `Petición ${id}`, category: 'Películas', requested_source: null, requested_resolution: null,
  emu_status: 'unfilled', points: null, comments: null, votes: null, author: 'pedidor', is_mine: false, req_scope: null,
  req_season: null, req_episode: null, created_at: '2026-10-01T00:00:00Z', tmdb_id: null, imdb_id: null, tvdb_id: null,
  mal_id: null, url: null, compatibility_status: null, compatibility_confidence: null, library_item_id: null,
  library_title: null, library_year: null, instance_type: null, instance_name: null, instance_id: null, title_slug: null,
  library_tmdb_id: null, display_title: null, local_status: null, poster_url: null, backdrop_url: null, reviewed_at: null,
  updated_at: null, readiness_status: null, readiness_action: null, readiness_best_library_item_id: null, ...extra,
}) as RequestItemResponse

const DATOS = [
  peticion(1, { readiness_status: 'no_local_match', compatibility_status: 'Sin coincidencia', points: 500 }),
  peticion(2, { readiness_status: 'ready_to_upload', compatibility_status: 'Compatible', points: 40 }),
  peticion(3, { readiness_status: 'no_castellano', compatibility_status: 'Compatible', points: 90 }),
  peticion(4, { readiness_status: 'ready_to_upload', compatibility_status: 'Compatible', points: 300 }),
  peticion(5, { readiness_status: 'filled', compatibility_status: 'Llena', points: 999 }),
  peticion(6, { readiness_status: 'no_local_match', compatibility_status: 'Sin coincidencia', points: 20 }),
]

async function pagina() {
  await montar(
    <SyncContext.Provider value={{
      requestsSyncing: false, requestsStatus: null, startRequestsSync: vi.fn(), lastInvalidatedAt: 0, isAnySyncing: false,
    } as never}>
      <SeccionVisible visible><RequestsPage /></SeccionVisible>
    </SyncContext.Provider>,
  )
  await esperar(() => document.querySelector('table.data-table tbody tr'))
}

const grupos = () => [...document.querySelectorAll('tbody.pet-bloque')].map(b => ({
  titulo: b.querySelector('.pet-grupo-titulo')!.textContent,
  n: b.querySelector('.pet-grupo-n')!.textContent,
  filas: [...b.querySelectorAll('tr.clickable')].map(tr => tr.querySelector('.lib-title-link')!.textContent),
}))
const ultimaLlamada = () => { const l = vi.mocked(getRequests).mock.calls; return l[l.length - 1][0] }

beforeEach(() => {
  localStorage.clear()
  vi.mocked(getRequests).mockResolvedValue({ items: DATOS, total: DATOS.length } as never)
  vi.mocked(getInstances).mockResolvedValue([])
})
afterEach(desmontar)

describe('Peticiones', () => {
  it('sin orden elegido agrupa por lo que se puede hacer y ordena cada grupo por recompensa', async () => {
    await pagina()
    expect(grupos()).toEqual([
      { titulo: 'Lista para subir', n: '2', filas: ['Petición 4', 'Petición 2'] },
      { titulo: 'Parcial', n: '1', filas: ['Petición 3'] },
      { titulo: 'No la tienes', n: '2', filas: ['Petición 1', 'Petición 6'] },
      { titulo: 'Cerradas', n: '1', filas: ['Petición 5'] },
    ])
    // Al servidor se le pide por recompensa: es el orden de dentro de cada grupo.
    expect(vi.mocked(getRequests).mock.calls[0][0]).toMatchObject({ sort: 'points_desc' })
  })

  it('elegir otro orden quita los grupos y deja la lista plana', async () => {
    await pagina()
    await elegir(document.querySelector('select.form-select') as HTMLSelectElement, 'created_desc')
    await esperar(() => document.querySelectorAll('tbody.pet-bloque').length === 0)
    expect(document.querySelectorAll('tr.clickable')).toHaveLength(DATOS.length)
    expect(document.querySelector('.pet-grupo-cab')).toBeNull()
    expect(ultimaLlamada()).toMatchObject({ sort: 'created_desc' })
  })

  it('ordenar desde la cabecera de Puntos también quita los grupos', async () => {
    await pagina()
    await pulsar(document.querySelector('button[aria-label="Puntos / recompensa"]')!)
    await esperar(() => document.querySelectorAll('tbody.pet-bloque').length === 0)
    expect(ultimaLlamada()).toMatchObject({ sort: 'points_desc' })
  })
})
