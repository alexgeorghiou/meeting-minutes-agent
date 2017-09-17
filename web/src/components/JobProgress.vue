<script setup lang="ts">
import { computed } from 'vue'
import type { Job } from '../types'

const props = defineProps<{ job: Job }>()

const STAGE_LABELS: Record<string, string> = {
  transcribe: 'Transcribing audio',
  prepare: 'Cleaning and chunking transcript',
  summarize: 'Summarising discussion',
  extract_decisions: 'Extracting decisions',
  extract_action_items: 'Extracting action items',
  normalize: 'Resolving owners and due dates',
  review: 'Reviewing results',
  finalize: 'Assembling minutes',
  done: 'Done',
}

const percent = computed(() => Math.round(props.job.progress * 100))
const label = computed(() => {
  if (props.job.status === 'failed') return 'Failed'
  if (props.job.status === 'queued') return 'Queued'
  return STAGE_LABELS[props.job.stage ?? ''] ?? 'Working'
})
</script>

<template>
  <section class="card progress" :class="job.status">
    <header>
      <strong>{{ job.title || job.source }}</strong>
      <span class="badge">{{ job.status }}</span>
    </header>
    <div
      class="bar"
      role="progressbar"
      :aria-valuenow="percent"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div class="fill" :style="{ width: `${percent}%` }" />
    </div>
    <p class="muted">{{ label }} · {{ percent }}%</p>
    <p v-if="job.error" class="error">{{ job.error }}</p>
  </section>
</template>
