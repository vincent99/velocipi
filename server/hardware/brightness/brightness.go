package brightness

import (
	"math"
	"os"
	"path"
	"strconv"
	"strings"
	"time"

	"github.com/vincent99/velocipi/server/hardware/lightsensor"
)

const (
	DEFAULT_DEVICE = "/sys/class/backlight/10-0045"
	DESIRED        = "brightness"
	MAX            = "max_brightness"
	STEPS          = 10
)

type Handler func(*Brightness, Result)

type Brightness struct {
	device    string
	sensor    *lightsensor.LightSensor
	listeners []Handler

	minBrightness int
	maxBrightness int
	minLux        float64
	maxLux        float64

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
	MinLux        float64
	MaxLux        float64
}

type Result struct {
	Brightness int     `json:"brightness"`
	Percent    float64 `json:"percent"`
	Lux        float64 `json:"lux"`
}

func NewBrightness(opt *Config) (*Brightness, error) {
	dev := opt.Device
	if dev == "" {
		dev = DEFAULT_DEVICE
	}

	speed := opt.Speed
	if speed == 0 {
		speed = 1000
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

func (b *Brightness) Init() error {
	b.ticker = time.NewTicker(time.Duration(b.speed) * time.Millisecond)
	quit := make(chan struct{})

	go func() {
		for {
			select {
			case <-b.ticker.C:
				val := b.Read()

				b.update(val)
			case <-quit:
				b.ticker.Stop()
				return
			}
		}
	}()

	return nil
}

func (b *Brightness) Read() Result {
	brightness := 0
	percent := 0.0
	ambient, _ := b.sensor.GetAmbientLux()

	//fmt.Println("Params: ", v.minBrightness, v.maxBrightness, v.minLux, v.maxLux)
	if ambient <= b.minLux {
		brightness = b.minBrightness
		percent = 0
	} else if ambient >= b.maxLux {
		brightness = b.maxBrightness
		percent = 1
	} else {
		percent = float64(ambient-b.minLux) / float64(b.maxLux-b.minLux)
		brightness = b.minBrightness + int(math.Round(float64(b.maxBrightness-b.minBrightness)*percent))
	}

	return Result{
		Brightness: brightness,
		Percent:    100 * percent,
		Lux:        ambient,
	}
}

func (b *Brightness) Listen(h Handler) {
	b.listeners = append(b.listeners, h)
	val := b.Read()
	h(b, val)
}

func (b *Brightness) Stop() {
	if b.ticker != nil {
		b.ticker.Stop()
	}

	if b.changer != nil {
		b.changer.Stop()
	}

	b.listeners = nil
}

func (b *Brightness) update(val Result) {
	if b.target == val.Brightness {
		return
	}

	b.target = val.Brightness
	step := float64(val.Brightness-b.current) / STEPS
	if step > 0 {
		step = math.Ceil(step)
	} else {
		step = math.Floor(step)
	}

	if b.changer != nil {
		b.changer.Stop()
	}

	if step == 0 || b.current == b.target {
		return
	}

	for i := range b.listeners {
		b.listeners[i](b, val)
	}

	//fmt.Println("Updating", v.speed, STEPS, step, time.Duration(v.speed)*time.Second/STEPS)
	b.changer = time.NewTicker(time.Duration(b.speed) * time.Millisecond / STEPS)

	quit := make(chan struct{})
	go func() {

		for {
			select {
			case <-b.changer.C:
				neu := int(math.Round(float64(b.current) + step))
				if (step > 0 && neu >= b.target) || (step < 0 && neu <= b.target) {
					neu = b.target
				}

				//fmt.Println("Update", step, v.current, neu, v.target)
				b.set(neu)

				if neu == b.target {
					<-quit
				}

			case <-quit:
				b.changer.Stop()
				return
			}
		}
	}()
}

func (b *Brightness) set(brightness int) error {
	if brightness < b.minBrightness {
		brightness = b.minBrightness
	} else if brightness > b.maxBrightness {
		brightness = b.maxBrightness
	}

	err := os.WriteFile(path.Join(b.device, DESIRED), []byte(strconv.Itoa(brightness)), 0600)
	b.current = brightness

	//fmt.Print("Set", brightness)
	return err
}
