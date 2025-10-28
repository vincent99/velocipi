<script setup lang="ts">
import { computed, PropType } from 'vue';
import { Tire } from '../../types/tire';

  const {label, tire} = defineProps({
    label: { type: String, required: true },
    tire: { type: Object as PropType<Tire>, required: true },
  })

  function ucFirst(str: string) {
    return str.substring(0,1).toUpperCase() + str.substring(1)
  }

  function zeroPad(num: number): string {
    if ( num < 10 ) {
      return "0" + num
    }

    return `${num}`
  }

  const age = computed(() => {
    const d = new Date(Date.parse(tire.updated))
    let out = ""
    let h = d.getHours()
    if ( h === 0 ) {
      h = 12
    } else if ( h > 12 ) {
      h -= 12;
    }
    const m = d.getMinutes()
    const s = d.getSeconds()

    return `${zeroPad(h)}:${zeroPad(m)}:${zeroPad(s)}`
 })

</script>

<template>
  <div class="label">{{label}}</div>
  <div v-if="tire.position">
    <div>{{tire.pressurePsi}} PSI</div>
    <div>{{tire.tempF}}°F</div>
    <div>{{tire.battery}}%</div>
    <div>{{ucFirst(tire.inflation)}}</div>
    <div>{{ucFirst(tire.rotation)}}</div>
    <div>{{age}}</div>
  </div>
  <div v-else>
      ???
  </div>
</template>

<style type="css" scoped>
  .label {
    font-weight: italic;
  };
</style>
