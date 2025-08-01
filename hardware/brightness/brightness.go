package brightness

import (
	"fmt"
	"math"
	"os"
	"path"
	"strconv"
	"strings"
	"time"
	"velocity/hardware/lightsensor"
)

const (
	DEFAULT_DEVICE = "/sys/class/backlight/10-0045"
	DESIRED        = "brightness"
	MAX            = "max_brightness"
	STEPS          = 10
)

type Brightness struct {
	device string
	sensor *lightsensor.LightSensor

	minBrightness int
	maxBrightness int
	minLux        int
	maxLux        int

	ticker  *time.Ticker
	changer *time.Ticker
	speed   int
	current int
	target  int
}

type Config struct {
	Device        string
	Sensor        *lightsensor.LightSensor
	Speed         int
	MinBrightness int
	MaxBrightness int
	MinLux        int
	MaxLux        int
}

func NewBrightness(opt *Config) (*Brightness, error) {
	dev := opt.Device
	if dev == "" {
		dev = DEFAULT_DEVICE
	}

	speed := opt.Speed
	if speed == 0 {
		speed = 5
	}

	minBrightness := opt.MinBrightness
	if minBrightness == 0 {
		minBrightness = 1
	}

	maxBrightness := opt.MaxBrightness
	if maxBrightness == 0 {
		bytes, err := os.ReadFile(path.Join(dev, MAX))
		if err != nil {
			return nil, err
		}

		val, err := strconv.Atoi(strings.TrimSpace(string(bytes)))
		if err != nil {
			return nil, err
		}

		maxBrightness = val
	}

	minLux := opt.MinLux
	maxLux := opt.MaxLux
	if maxLux == 0 {
		maxLux = 100
	}

	v := &Brightness{
		sensor:        opt.Sensor,
		device:        dev,
		speed:         speed,
		minBrightness: minBrightness,
		maxBrightness: maxBrightness,
		minLux:        minLux,
		maxLux:        maxLux,
	}

	return v, v.Init()
}

func (v *Brightness) Init() error {
	v.ticker = time.NewTicker(time.Duration(v.speed) * time.Second)
	quit := make(chan struct{})

	go func() {
		for {
			select {
			case <-v.ticker.C:
				brightness := 0
				ambient, _ := v.sensor.GetAmbientLux()

				fmt.Println("Params: ", v.minBrightness, v.maxBrightness, v.minLux, v.maxLux)
				if ambient <= v.minLux {
					brightness = v.minBrightness
				} else if ambient >= v.maxLux {
					brightness = v.maxBrightness
				} else {
					percent := float64(ambient-v.minLux) / float64(v.maxLux-v.minLux)
					brightness = v.minBrightness + int(math.Round(float64(v.maxBrightness-v.minBrightness)*percent))
				}

				v.update(brightness)
			case <-quit:
				v.ticker.Stop()
				return
			}
		}
	}()

	return nil
}

func (v *Brightness) Stop() {
	if v.ticker != nil {
		v.ticker.Stop()
	}

	if v.changer != nil {
		v.changer.Stop()
	}
}

func (v *Brightness) update(target int) {
	if v.target == target {
		return
	}

	v.target = target
	step := float64(target-v.current) / STEPS

	if v.changer != nil {
		v.changer.Stop()
	}

	if step == 0 || v.current == v.target {
		return
	}

	fmt.Println("Updating", v.speed, STEPS, step, time.Duration(v.speed)*time.Second/STEPS)
	v.changer = time.NewTicker(time.Duration(v.speed) * time.Second / STEPS)

	quit := make(chan struct{})
	go func() {

		for {
			select {
			case <-v.changer.C:
				neu := int(math.Round(float64(v.current) + step))

				fmt.Println("Update", step, v.current, neu, v.target)
				v.set(neu)

				if (step > 0 && neu >= v.target) || (step < 0 && neu <= v.target) {
					<-quit
				}

			case <-quit:
				v.changer.Stop()
				return
			}
		}
	}()
}

func (v *Brightness) set(brightness int) error {
	if brightness < v.minBrightness {
		brightness = v.minBrightness
	} else if brightness > v.maxBrightness {
		brightness = v.maxBrightness
	}

	err := os.WriteFile(path.Join(v.device, DESIRED), []byte(strconv.Itoa(brightness)), 0600)
	v.current = brightness
	fmt.Printf("Set", brightness)
	return err
}
