  export interface Tire {
    position: "FL"|"FR"|"RL"|"RR"
    serial: string
    updated: string
    tempC: number
    tempF: number
    pressureKpa: number
    pressureBar: number
    pressurePsi: number
    voltage: number
    battery: number
    inflation: "flat"|"low"|"decreasing"|"stable"
    rotation: "unknown"|"still"|"starting"|"rolling"
  }
