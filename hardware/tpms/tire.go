package tpms

import (
	"fmt"
	"time"
)

const BATT_100 = 31 // in 0.1V
const BATT_0 = 26 // in 0.1V
const TEMP_OFFSET = 20 // in °C
const PRESSURE_0 = 146 // in 0.1Kpa

type InflationState string
const (
	FLAT InflationState = "flat"
	LOW InflationState = "low"
	DECREASING InflationState = "decreasing"
	STABLE InflationState = "stable"
	RISING InflationState = "rising"
)

type RotationState string
const (
	UNKNOWN RotationState = "unknown"
	STILL RotationState = "still"
	STARTING RotationState = "starting"
	ROLLING RotationState = "rolling"
)


type Tire struct {
	Position string `json:"position"`
	Serial string `json:"serial"`
	Updated time.Time `json:"updated"`

	TempC float32 `json:"tempC"`
	TempF float32 `json:"tempF"`

	PressureKpa float32 `json:"pressureKpa"`
	PressureBar float32 `json:"pressureBar"`
	PressurePsi float32 `json:"pressurePsi"`

	Voltage float32 `json:"voltage"`
	Battery float32 `json:"battery"`

	Inflation InflationState `json:"inflation"`
	Rotation RotationState `json:"rotation"`
}

func NewTire(position string, serial string) *Tire {
	return &Tire{
		Position: position,
		Serial: serial,
	}
}

func (t *Tire) String() string {
	out := ""

	if t.Position == "" {
		out += "[" + t.Serial + "]: "
	} else {
		out += t.Position + ": "
	}

	out += fmt.Sprintf("Bat: %3.0f%%", t.Battery) +
		fmt.Sprintf(", Temp: %.1f°F", t.TempF) +
		fmt.Sprintf(", Pres: %3.1f PSI (%3.1f)", t.PressurePsi, t.PressureKpa) +
		fmt.Sprintf(", Inflation: %10s", string(t.Inflation)) +
		fmt.Sprintf(", Rotation: %10s", string(t.Rotation)) +
		fmt.Sprintf(", Age: %.1fs", t.Age().Seconds())

		return out
}

func (t *Tire) Update(status uint8, voltage uint8, temperature uint8, pressure uint16) {
	t.Updated = time.Now()

	t.TempC =  float32(temperature)/10.0 + TEMP_OFFSET
	t.TempF = t.TempC*9.0/5.0 + 32.0

	if pressure <= PRESSURE_0  {
		t.PressureKpa = 0
	} else {
		t.PressureKpa = float32(pressure)/10.0
	}

	t.PressurePsi = t.PressureKpa / 6.89476
	t.PressureBar = t.PressureKpa / 10.0

	t.Voltage = float32(voltage)/10.0

	if voltage <= BATT_0 {
		t.Battery = 0
	} else if voltage >= BATT_100 {
		t.Battery = 100
	} else {
		t.Battery = float32(voltage - BATT_0) * 100.0 / float32(BATT_100 - BATT_0)
	}

	if status & 0b10000000 > 0 {
		t.Inflation = FLAT
	} else if status & 0b00000010 > 0 {
		t.Inflation = LOW
	} else if status & 0b00001000 > 0 {
		t.Inflation = DECREASING
	} else if status & 0b00000100 > 0 {
		t.Inflation = RISING
	} else {
		t.Inflation = STABLE
	}

	if status & 0b00100000 > 0 {
		t.Rotation = STILL
	} else if status & 0b00010000 > 0 {
		t.Rotation = STARTING
	} else if status & 0b01000000 > 0 {
		t.Rotation = ROLLING
	} else {
		t.Rotation = UNKNOWN
	}
}

func (t *Tire) Age() time.Duration {
	return time.Since(t.Updated)
}
