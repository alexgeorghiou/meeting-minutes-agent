<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api'
import type { ActionItem, ActionItemPatch, Priority } from '../types'

const props = defineProps<{
  jobId: string
  items: ActionItem[]
  attendees: string[]
}>()

const emit = defineEmits<{
  updated: [item: ActionItem]
  removed: [itemId: string]
}>()

const saving = ref<Record<string, boolean>>({})
const error = ref<string | null>(null)
const priorities: Priority[] = ['low', 'medium', 'high']

function ownerOptions(item: ActionItem): string[] {
  const options = [...props.attendees]
  if (item.owner && !options.includes(item.owner)) options.push(item.owner)
  return options
}

async function save(item: ActionItem, patch: ActionItemPatch) {
  saving.value[item.id] = true
  error.value = null
  try {
    emit('updated', await api.updateActionItem(props.jobId, item.id, patch))
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value[item.id] = false
  }
}

function onDescription(item: ActionItem, event: Event) {
  const value = (event.target as HTMLInputElement).value.trim()
  if (value && value !== item.description) void save(item, { description: value })
}

function onOwner(item: ActionItem, event: Event) {
  const value = (event.target as HTMLSelectElement).value
  void save(item, { owner: value || null })
}

function onDueDate(item: ActionItem, event: Event) {
  const value = (event.target as HTMLInputElement).value
  void save(item, { due_date: value || null })
}

function onPriority(item: ActionItem, event: Event) {
  void save(item, { priority: (event.target as HTMLSelectElement).value as Priority })
}

async function remove(item: ActionItem) {
  if (!confirm(`Delete "${item.description}"?`)) return
  try {
    await api.deleteActionItem(props.jobId, item.id)
    emit('removed', item.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}
</script>

<template>
  <div class="action-items">
    <p v-if="items.length === 0" class="muted">No action items were found.</p>
    <table v-else>
      <thead>
        <tr>
          <th class="narrow">Done</th>
          <th>Task</th>
          <th>Owner</th>
          <th>Due</th>
          <th>Priority</th>
          <th class="narrow" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.id" :class="{ done: item.done, saving: saving[item.id] }">
          <td class="narrow">
            <input
              type="checkbox"
              :checked="item.done"
              :aria-label="`Mark ${item.description} done`"
              @change="save(item, { done: !item.done })"
            />
          </td>
          <td>
            <input class="plain" type="text" :value="item.description" @change="onDescription(item, $event)" />
          </td>
          <td>
            <select :value="item.owner ?? ''" :class="{ warn: !item.owner }" @change="onOwner(item, $event)">
              <option value="">Unassigned</option>
              <option v-for="name in ownerOptions(item)" :key="name" :value="name">{{ name }}</option>
            </select>
          </td>
          <td>
            <input type="date" :value="item.due_date ?? ''" @change="onDueDate(item, $event)" />
            <small v-if="item.due_text" class="muted">“{{ item.due_text }}”</small>
          </td>
          <td>
            <select :value="item.priority" :class="`priority-${item.priority}`" @change="onPriority(item, $event)">
              <option v-for="p in priorities" :key="p" :value="p">{{ p }}</option>
            </select>
          </td>
          <td class="narrow">
            <button type="button" class="icon" title="Delete" @click="remove(item)">✕</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>
