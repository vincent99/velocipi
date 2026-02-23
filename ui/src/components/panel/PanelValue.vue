<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    col: number;
    row: number;
    colSpan?: number;
    rowSpan?: number;
    label?: string;
    icon?: string; // uicons class suffix e.g. "clock"
    modelValue?: string;
    labelAlign?: 'left' | 'center' | 'right';
    valueAlign?: 'left' | 'center' | 'right';
    minLabelWidth?: number;
  }>(),
  {
    colSpan: 1,
    rowSpan: 1,
    label: undefined,
    icon: undefined,
    modelValue: undefined,
    labelAlign: undefined,
    valueAlign: undefined,
    minLabelWidth: undefined,
  }
);

const tall = computed(() => (props.rowSpan ?? 1) >= 2);

const effectiveLabelAlign = computed(
  () => props.labelAlign ?? (tall.value ? 'center' : 'left')
);
const effectiveValueAlign = computed(
  () => props.valueAlign ?? (tall.value ? 'center' : 'right')
);

const gridStyle = computed(() => ({
  gridColumn: `${props.col} / span ${props.colSpan}`,
  gridRow: `${props.row} / span ${props.rowSpan}`,
}));
</script>

<template>
  <div :style="gridStyle" :class="['panel-value', { tall }]">
    <div v-if="tall" :class="['pv-value', `align-${effectiveValueAlign}`]">
      <slot>{{ modelValue }}</slot>
    </div>
    <div
      v-if="label || icon"
      :class="['pv-label', `align-${effectiveLabelAlign}`]"
      :style="minLabelWidth ? { minWidth: minLabelWidth + 'px' } : undefined"
    >
      <i v-if="icon" :class="`fi-sr-${icon}`" class="pv-icon" />
      <span v-if="label" class="pv-label-text">{{ label }}</span>
    </div>
    <div v-if="!tall" :class="['pv-value', `align-${effectiveValueAlign}`]">
      <slot>{{ modelValue }}</slot>
    </div>
  </div>
</template>

<style scoped lang="scss">
.panel-value {
  display: flex;
  align-items: center;
  overflow: hidden;
  box-sizing: border-box;
  // Non-interactive: border matches background so grid cells align with bordered controls.
  border: 1px solid var(--panel-control-bg, #000000);
  background: var(--panel-control-bg, #000000);
  color: var(--panel-control-text, #ffffff);
  font-size: 11px;
  gap: 2px;

  // 1-row: horizontal layout — label left, value right
  &:not(.tall) {
    flex-direction: row;
    padding: 0 2px;

    .pv-label {
      display: flex;
      align-items: center;
      gap: 2px;
      flex-shrink: 0;
    }

    .pv-value {
      flex: 1;
      min-width: 0;
    }
  }

  // multi-row: vertical layout — value top, label bottom
  &.tall {
    flex-direction: column;
    justify-content: center;
    padding: 1px;

    .pv-label {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 2px;
      width: 100%;
    }

    .pv-value {
      width: 100%;
    }
  }
}

.pv-value {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1;
}

.pv-label-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1;
  font-size: 9px;
  opacity: 0.7;
}

.pv-icon {
  font-size: 9px;
  flex-shrink: 0;
  line-height: 1;
  opacity: 0.7;
}

.align-left {
  text-align: left;
  justify-content: flex-start;
}
.align-center {
  text-align: center;
  justify-content: center;
}
.align-right {
  text-align: right;
  justify-content: flex-end;
}
</style>
