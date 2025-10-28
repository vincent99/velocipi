<script setup lang="ts">
import { PropType } from 'vue';
import { Tire } from '../../types/tire';

  const {label, tire} = defineProps({
    label: { type: String, required: true },
    tire: { type: Object as PropType<Tire>, required: true },
  })

  function ucFirst(str: string) {
    return str.substring(0,1).toUpperCase() + str.substring(1)
  }

</script>

<template>
  <div class="label">{{label}}</div>
  <div v-if="tire.position">
    <div>{{tire.pressurePsi}} PSI</div>
    <div>{{tire.tempF}}°F</div>
    <div>{{tire.battery}}%</div>
    <div>{{ucFirst(tire.inflation)}}</div>
    <div>{{ucFirst(tire.rotation)}}</div>
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
