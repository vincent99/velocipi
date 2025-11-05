<script setup lang="ts">
import { computed, onBeforeUnmount, PropType, ref } from 'vue';
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


 function formatter(val: number): string {
  if ( !tire?.position ) {
    return '???'
  }

  return `${val}`
 }

const now = ref<number>(new Date().getTime())
const timer = setInterval(() => {
  now.value = new Date().getTime()
}, 1000)

onBeforeUnmount(() => {
  clearInterval(timer)
})

 const style = computed(() => {
  if (!tire?.position ) {
    return 'background-color: red'
  }

  if ( tire.pressurePsi < 10 ) {
    return 'background-color: red'
  } else if ( tire.pressurePsi < 20 ) {
    return 'background-color: orange'
  }

  const age = now.value - Date.parse(tire.updated)
  if ( age > 5 * 60 * 1000 ) {
    return 'background-color: red'
  }

  return ''
 })

</script>

<template>
  <el-col :span="3" class="text-center mb-4">
    <el-statistic :title="label" :value="tire.pressurePsi" :formatter="formatter" suffix="psi" :style="style"/>
  </el-col>
</template>
