import { useEffect, useRef } from 'react'
import { useSignIn } from '@/api/hooks'

// Google Identity Services: Google renders the button, then hands us a signed credential (ID token)
// that the API verifies before opening a session. https://developers.google.com/identity/gsi/web
type Gsi = {
  initialize(options: { client_id: string; callback: (r: { credential: string }) => void }): void
  renderButton(parent: HTMLElement, options: Record<string, string | number>): void
}

declare global {
  interface Window {
    google?: { accounts: { id: Gsi } }
  }
}

let script: Promise<void> | undefined

function loadGsi(): Promise<void> {
  script ??= new Promise((resolve, reject) => {
    const tag = document.createElement('script')
    tag.src = 'https://accounts.google.com/gsi/client'
    tag.async = true
    tag.onload = () => resolve()
    tag.onerror = () => reject(new Error('could not load Google sign-in'))
    document.head.appendChild(tag)
  })
  return script
}

export function GoogleButton({ clientId }: { clientId: string }) {
  const parent = useRef<HTMLDivElement>(null)
  const { mutate } = useSignIn()

  useEffect(() => {
    let live = true
    void loadGsi().then(() => {
      const gsi = window.google?.accounts.id
      if (!live || !gsi || !parent.current) return
      gsi.initialize({ client_id: clientId, callback: (r) => mutate(r.credential) })
      gsi.renderButton(parent.current, {
        theme: 'filled_black',
        size: 'large',
        shape: 'pill',
        text: 'signin_with',
        locale: 'en',
      })
    })
    return () => {
      live = false
    }
  }, [clientId, mutate])

  return <div ref={parent} className="min-h-10" />
}
