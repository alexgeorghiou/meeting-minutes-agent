<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from './api'
import ExportPanel from './components/ExportPanel.vue'
import JobProgress from './components/JobProgress.vue'
import MinutesView from './components/MinutesView.vue'
import UploadForm from './components/UploadForm.vue'
import { useJobPolling } from './composables/useJobPolling'
import type { Health, Job, Minutes } from './types'

const jobId = ref<string | null>(new URLSearchParams(location.search).get('job'))
const minutes = ref<Minutes | null>(null)
const minutesError = ref<string | null>(null)
const health = ref<Health | null>(null)
const recent = ref<Job[]>([])

const { job, error: pollError } = useJobPolling(jobId)

onMounted(async () => {
  try {
    health.value = await api.health()
    recent.value = await api.jobs(5)
  } catch {
    health.value = null
  }
})

watch(jobId, (id) => {
  const url = new URL(location.href)
  if (id) url.searchParams.set('job', id)
  else url.searchParams.delete('job')
  history.replaceState(null, '', url)
  minutes.value = null
})

watch(
  () => job.value?.status,
  async (status) => {
    if (status !== 'completed' || !jobId.value) return
    try {
      minutes.value = await api.minutes(jobId.value)
      minutesError.value = null
    } catch (e) {
      minutesError.value = e instanceof Error ? e.message : String(e)
    }
  },
)

function onSubmitted(submitted: Job) {
  jobId.value = submitted.id
  recent.value = [submitted, ...recent.value.filter((j) => j.id !== submitted.id)].slice(0, 5)
}

function reset() {
  jobId.value = null
}
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <h1>Meeting Minutes Agent</h1>
      <p v-if="health" class="muted">
        LLM: <code>{{ health.llm }}</code> · Transcriber: <code>{{ health.transcriber }}</code>
      </p>
      <p v-else class="error">API unreachable</p>
    </header>

    <main>
      <template v-if="!jobId">
        <UploadForm @submitted="onSubmitted" />
        <section v-if="recent.length" class="card recent">
          <h3>Recent meetings</h3>
          <ul>
            <li v-for="item in recent" :key="item.id">
              <a href="#" @click.prevent="jobId = item.id">{{ item.title || item.source }}</a>
              <span class="badge">{{ item.status }}</span>
            </li>
          </ul>
        </section>
      </template>

      <template v-else>
        <button type="button" class="link" @click="reset">← New meeting</button>
        <p v-if="pollError" class="error">{{ pollError }}</p>
        <JobProgress v-if="job && job.status !== 'completed'" :job="job" />
        <p v-if="minutesError" class="error">{{ minutesError }}</p>
        <div v-if="minutes && jobId" class="result-grid">
          <MinutesView :job-id="jobId" :minutes="minutes" @change="minutes = $event" />
          <ExportPanel :job-id="jobId" />
        </div>
      </template>
    </main>
  </div>
</template>
