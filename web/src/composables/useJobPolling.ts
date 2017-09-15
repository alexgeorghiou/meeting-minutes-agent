import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { api } from '../api'
import type { Job } from '../types'

const FINISHED = new Set(['completed', 'failed'])

/**
 * Polls `/api/jobs/{id}` until the job finishes, backing off gently while it runs.
 */
export function useJobPolling(jobId: Ref<string | null>, intervalMs = 1000) {
  const job = ref<Job | null>(null)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined
  let attempt = 0

  function stop() {
    if (timer !== undefined) {
      clearTimeout(timer)
      timer = undefined
    }
  }

  async function tick(id: string) {
    try {
      const current = await api.job(id)
      if (jobId.value !== id) return // a newer job replaced this one
      job.value = current
      error.value = null
      if (FINISHED.has(current.status)) return
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
    attempt += 1
    const delay = Math.min(intervalMs * (1 + attempt * 0.25), 5000)
    timer = setTimeout(() => void tick(id), delay)
  }

  watch(
    jobId,
    (id) => {
      stop()
      job.value = null
      attempt = 0
      if (id) void tick(id)
    },
    { immediate: true },
  )

  onBeforeUnmount(stop)

  return { job, error, stop }
}
