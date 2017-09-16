<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api'
import type { Job } from '../types'

const emit = defineEmits<{ submitted: [job: Job] }>()

type Mode = 'audio' | 'transcript'

const mode = ref<Mode>('audio')
const file = ref<File | null>(null)
const transcript = ref('')
const title = ref('')
const meetingDate = ref(new Date().toISOString().slice(0, 10))
const attendees = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const dragging = ref(false)

const canSubmit = computed(() =>
  !busy.value && (mode.value === 'audio' ? file.value !== null : transcript.value.trim().length > 0),
)

function pick(event: Event) {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
}

function drop(event: DragEvent) {
  dragging.value = false
  const dropped = event.dataTransfer?.files?.[0]
  if (dropped) file.value = dropped
}

async function submit() {
  if (!canSubmit.value) return
  busy.value = true
  error.value = null
  const options = {
    title: title.value.trim() || undefined,
    meetingDate: meetingDate.value || undefined,
    attendees: attendees.value.trim() || undefined,
  }
  try {
    const job =
      mode.value === 'audio' && file.value
        ? await api.uploadAudio(file.value, options)
        : await api.submitTranscript(transcript.value, options)
    emit('submitted', job)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="card upload" @submit.prevent="submit">
    <div class="tabs" role="tablist">
      <button type="button" :class="{ active: mode === 'audio' }" @click="mode = 'audio'">
        Upload recording
      </button>
      <button type="button" :class="{ active: mode === 'transcript' }" @click="mode = 'transcript'">
        Paste transcript
      </button>
    </div>

    <label
      v-if="mode === 'audio'"
      class="dropzone"
      :class="{ dragging }"
      @dragover.prevent="dragging = true"
      @dragleave="dragging = false"
      @drop.prevent="drop"
    >
      <input type="file" accept="audio/*,video/mp4,video/webm,.txt" @change="pick" />
      <span v-if="file">{{ file.name }} ({{ (file.size / 1_048_576).toFixed(1) }} MB)</span>
      <span v-else>Drop an audio file here or click to browse</span>
    </label>

    <textarea
      v-else
      v-model="transcript"
      rows="8"
      placeholder="Priya: We decided to ship on Wednesday.&#10;Lena: I'll fix the export bug by Friday."
    />

    <div class="grid">
      <label>
        Title
        <input v-model="title" type="text" placeholder="Release planning sync" />
      </label>
      <label>
        Meeting date
        <input v-model="meetingDate" type="date" />
      </label>
      <label class="wide">
        Attendees
        <input v-model="attendees" type="text" placeholder="Priya, Marco, Lena (optional)" />
      </label>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <button class="primary" type="submit" :disabled="!canSubmit">
      {{ busy ? 'Uploading…' : 'Generate minutes' }}
    </button>
  </form>
</template>
