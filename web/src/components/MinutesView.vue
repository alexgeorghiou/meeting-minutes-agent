<script setup lang="ts">
import { computed } from 'vue'
import type { ActionItem, Minutes } from '../types'
import ActionItemsEditor from './ActionItemsEditor.vue'

const props = defineProps<{ jobId: string; minutes: Minutes }>()
const emit = defineEmits<{ change: [minutes: Minutes] }>()

const formattedDate = computed(() =>
  new Date(`${props.minutes.meeting_date}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }),
)

const openCount = computed(() => props.minutes.action_items.filter((i) => !i.done).length)

function onUpdated(item: ActionItem) {
  emit('change', {
    ...props.minutes,
    action_items: props.minutes.action_items.map((i) => (i.id === item.id ? item : i)),
  })
}

function onRemoved(itemId: string) {
  emit('change', {
    ...props.minutes,
    action_items: props.minutes.action_items.filter((i) => i.id !== itemId),
  })
}
</script>

<template>
  <article class="card minutes">
    <header>
      <h2>{{ minutes.title }}</h2>
      <p class="muted">
        {{ formattedDate }}
        <template v-if="minutes.attendees.length"> · {{ minutes.attendees.join(', ') }}</template>
      </p>
    </header>

    <section>
      <h3>Summary</h3>
      <p>{{ minutes.summary || 'No summary.' }}</p>
      <ul v-if="minutes.key_points.length" class="key-points">
        <li v-for="point in minutes.key_points" :key="point">{{ point }}</li>
      </ul>
    </section>

    <section>
      <h3>Decisions <span class="count">{{ minutes.decisions.length }}</span></h3>
      <p v-if="minutes.decisions.length === 0" class="muted">No decisions recorded.</p>
      <ol v-else class="decisions">
        <li v-for="decision in minutes.decisions" :key="decision.id">
          <strong>{{ decision.summary }}</strong>
          <span v-if="decision.made_by" class="muted"> — {{ decision.made_by }}</span>
          <p v-if="decision.rationale" class="muted">Why: {{ decision.rationale }}</p>
        </li>
      </ol>
    </section>

    <section>
      <h3>Action items <span class="count">{{ openCount }} open</span></h3>
      <ActionItemsEditor
        :job-id="jobId"
        :items="minutes.action_items"
        :attendees="minutes.attendees"
        @updated="onUpdated"
        @removed="onRemoved"
      />
    </section>

    <section v-if="minutes.review_notes.length" class="review">
      <h3>Needs review</h3>
      <ul>
        <li v-for="note in minutes.review_notes" :key="note">{{ note }}</li>
      </ul>
    </section>
  </article>
</template>
