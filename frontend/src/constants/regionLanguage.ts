// Region (ISO 3166-1) option list for Settings/setup — a broad practical
// set, not exhaustive. There's no language option: eMuwarez requires titles
// always in Spanish, so that's hardcoded (services/tmdb_titles.py), not a
// user setting.

export interface SelectOption {
  value: string
  label: string
}

export const REGION_OPTIONS: SelectOption[] = [
  { value: 'ES', label: 'España' },
  { value: 'MX', label: 'México' },
  { value: 'AR', label: 'Argentina' },
  { value: 'CO', label: 'Colombia' },
  { value: 'CL', label: 'Chile' },
  { value: 'PE', label: 'Perú' },
  { value: 'VE', label: 'Venezuela' },
  { value: 'UY', label: 'Uruguay' },
  { value: 'US', label: 'Estados Unidos' },
  { value: 'GB', label: 'Reino Unido' },
  { value: 'FR', label: 'Francia' },
  { value: 'DE', label: 'Alemania' },
  { value: 'IT', label: 'Italia' },
  { value: 'PT', label: 'Portugal' },
  { value: 'BR', label: 'Brasil' },
  { value: 'NL', label: 'Países Bajos' },
  { value: 'CA', label: 'Canadá' },
  { value: 'AU', label: 'Australia' },
  { value: 'JP', label: 'Japón' },
  { value: 'KR', label: 'Corea del Sur' },
]

export function findRegionLabel(value: string): string {
  return REGION_OPTIONS.find(o => o.value === value)?.label ?? value
}
