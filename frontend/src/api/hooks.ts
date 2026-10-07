import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, call, type ProfileInput } from './client'

const keys = {
  meta: ['meta'],
  profiles: ['profiles'],
  bookings: (id: number) => ['bookings', id],
  venues: (id: number) => ['venues', id],
}

const onError = (e: Error) => toast.error(e.message)

export const useMeta = () =>
  useQuery({ queryKey: keys.meta, queryFn: () => call(api.GET('/api/meta')) })

export const useProfiles = () =>
  useQuery({ queryKey: keys.profiles, queryFn: () => call(api.GET('/api/profiles')) })

export const useBookings = (profileId: number) =>
  useQuery({
    queryKey: keys.bookings(profileId),
    queryFn: () =>
      call(api.GET('/api/profiles/{profile_id}/bookings', { params: { path: { profile_id: profileId } } })),
    refetchInterval: 15_000, // races finish on their own; keep the page current
  })

export const useVenues = (profileId: number) =>
  useQuery({
    queryKey: keys.venues(profileId),
    queryFn: () =>
      call(api.GET('/api/profiles/{profile_id}/venues', { params: { path: { profile_id: profileId } } })),
    retry: false,
  })

export function useSaveProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: ProfileInput }) =>
      id === undefined
        ? call(api.POST('/api/profiles', { body }))
        : call(api.PUT('/api/profiles/{profile_id}', { params: { path: { profile_id: id } }, body })),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: keys.profiles })
      qc.invalidateQueries({ queryKey: keys.venues(p.id) })
      toast.success('Profile saved')
    },
    onError,
  })
}

export function useDeleteProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      call(api.DELETE('/api/profiles/{profile_id}', { params: { path: { profile_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.profiles }),
    onError,
  })
}

export function useSetCredentials(profileId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (values: Record<string, string>) =>
      call(
        api.PUT('/api/profiles/{profile_id}/credentials', {
          params: { path: { profile_id: profileId } },
          body: { values },
        }),
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.profiles })
      toast.success('Credentials stored (encrypted)')
    },
    onError,
  })
}

export function useSync(profileId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (refreshVenues: boolean) =>
      call(
        api.POST('/api/profiles/{profile_id}/sync', {
          params: { path: { profile_id: profileId }, query: { refresh_venues: refreshVenues } },
        }),
      ),
    onSuccess: (booking) => {
      qc.invalidateQueries({ queryKey: keys.bookings(profileId) })
      toast.success(booking ? `Planned: ${booking.title}` : 'No candidate event in your calendar')
    },
    onError,
  })
}

export function useRefreshVenues(profileId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      call(
        api.GET('/api/profiles/{profile_id}/venues', {
          params: { path: { profile_id: profileId }, query: { refresh: true } },
        }),
      ),
    onSuccess: (venues) => {
      qc.setQueryData(keys.venues(profileId), venues)
      toast.success(`${venues.length} venues in range`)
    },
    onError,
  })
}

export function useRetry(profileId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (bookingId: number) =>
      call(api.POST('/api/bookings/{booking_id}/retry', { params: { path: { booking_id: bookingId } } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.bookings(profileId) })
      toast.success('Race scheduled now')
    },
    onError,
  })
}
