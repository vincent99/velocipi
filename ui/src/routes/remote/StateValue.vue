<script setup lang="ts">
defineProps<{ value: unknown }>();

function objEntries(v: unknown): [string, unknown][] {
  return Object.entries(v as Record<string, unknown>);
}
</script>

<template>
  <span v-if="value === null || value === undefined" class="nil">—</span>
  <span v-else-if="typeof value !== 'object'" class="scalar">{{ value }}</span>
  <template v-else-if="Array.isArray(value)">
    <span v-if="value.length === 0" class="nil">[]</span>
    <table v-else>
      <tr v-for="(item, i) in value" :key="i">
        <td class="label">{{ i }}</td>
        <td><StateValue :value="item" /></td>
      </tr>
    </table>
  </template>
  <table v-else>
    <tr v-for="[k, v] in objEntries(value)" :key="k">
      <td class="label">{{ k }}</td>
      <td><StateValue :value="v" /></td>
    </tr>
  </table>
</template>

<style scoped lang="scss">
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 0.78rem;
}
td {
  padding: 0.15rem 0.5rem;
  vertical-align: top;
  border-bottom: 1px solid #1e1e1e;
}
td.label {
  color: #666;
  white-space: nowrap;
  width: 1%;
  padding-right: 0.75rem;
}
table table {
  background: rgba(255, 255, 255, 0.02);
  border-left: 2px solid #2a2a2a;
}
.nil {
  color: #3a3a3a;
}
.scalar {
  color: #ccc;
  word-break: break-all;
}
</style>
