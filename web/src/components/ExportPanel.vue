<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { ExportResult } from '../types'

const props = defineProps<{ jobId: string }>()

const LABELS: Record<string, string> = {
  markdown: 'Markdown',
  github: 'GitHub Issues',
  jira: 'Jira',
}

const targets = ref<string[]>([])
const running = ref<string | null>(null)
const result = ref<ExportResult | null>(null)
const error = ref<string | null>(null)
const copied = ref(false)

onMounted(async () => {
  try {
    targets.value = await api.exporters()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})

async function run(target: string) {
  if (
    target !== 'markdown' &&
    !confirm(`Create one ${LABELS[target] ?? target} issue per open action item?`)
  ) {
    return
  }
  running.value = target
  error.value = null
  result.value = null
  copied.value = false
  try {
    result.value = await api.exportTo(props.jobId, target)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    running.value = null
  }
}

async function copy() {
  if (!result.value?.content) return
  await navigator.clipboard.writeText(result.value.content)
  copied.value = true
}
</script>

<template>
  <aside class="card export">
    <h3>Export</h3>
    <div class="buttons">
      <button
        v-for="target in targets"
        :key="target"
        type="button"
        :disabled="running !== null"
        @click="run(target)"
      >
        {{ running === target ? 'Exporting…' : LABELS[target] ?? target }}
      </button>
      <a class="button secondary" :href="api.markdownUrl(jobId)" download>Download .md</a>
    </div>
    <p v-if="targets.length === 1" class="muted">
      Configure GitHub or Jira credentials on the server to enable issue export.
    </p>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="result" class="result">
      <template v-if="result.content">
        <div class="result-head">
          <span class="muted">{{ result.content_type }}</span>
          <button type="button" class="secondary" @click="copy">{{ copied ? 'Copied' : 'Copy' }}</button>
        </div>
        <pre>{{ result.content }}</pre>
      </template>
      <template v-else>
        <p>
          Created {{ result.issues.length }} issue(s)<template v-if="result.skipped.length">,
          skipped {{ result.skipped.length }} completed item(s)</template>.
        </p>
        <ul>
          <li v-for="issue in result.issues" :key="issue.key">
            <a :href="issue.url" target="_blank" rel="noopener">{{ issue.key }}</a>
          </li>
        </ul>
      </template>
    </div>
  </aside>
</template>
