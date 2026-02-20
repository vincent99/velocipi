import { ref } from 'vue'

const frameUrl = ref<string | null>(null)
let prevUrl: string | null = null
let ws: WebSocket | null = null

function connect() {
  ws = new WebSocket(`ws://${location.host}/screen`)
  ws.binaryType = 'blob'

  ws.onmessage = (e: MessageEvent<Blob>) => {
    const url = URL.createObjectURL(e.data)
    frameUrl.value = url
    if (prevUrl) URL.revokeObjectURL(prevUrl)
    prevUrl = url
  }

  ws.onerror = (e) => console.error('screen ws error', e)

  ws.onclose = () => setTimeout(connect, 2000)
}

export function useScreenSocket() {
  if (!ws) connect()
  return { frameUrl }
}
