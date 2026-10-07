import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

// Types come from FastAPI's OpenAPI schema: run `npm run gen:api` after changing the backend API.
export const api = createClient<paths>({ baseUrl: '/' })

type S = components['schemas']
export type Profile = S['ProfileOut']
export type ProfileInput = S['ProfileIn']
export type ProfileConfig = S['ProfileConfig']
export type Booking = S['BookingOut']
export type Venue = S['VenueOut']
export type Meta = S['MetaOut']

/** Unwrap an openapi-fetch result, turning FastAPI's `{detail}` errors into readable exceptions. */
export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request
  if (error !== undefined || !response.ok) {
    throw new Error(detail(error) ?? `${response.status} ${response.statusText}`)
  }
  return data as T
}

function detail(error: unknown): string | undefined {
  if (error && typeof error === 'object' && 'detail' in error) {
    const d = (error as { detail: unknown }).detail
    return typeof d === 'string' ? d : JSON.stringify(d)
  }
  return undefined
}
