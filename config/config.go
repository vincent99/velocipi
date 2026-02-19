package config

import (
	"log"
	"time"

	"github.com/joho/godotenv"
	"github.com/kelseyhightower/envconfig"
	"periph.io/x/conn/v3/physic"
)

// TireAddress maps one or more BT addresses (comma-separated in env) to a
// wheel position label. Each env var is TIRE_<POSITION>_ADDRS, e.g.:
//
//	TIRE_FL_ADDRS=4a:a0:00:00:eb:02,ae3806cb-ea50-2187-4d1d-10010147721a
type TireAddresses struct {
	FL []string `envconfig:"TIRE_FL_ADDRS"`
	FR []string `envconfig:"TIRE_FR_ADDRS"`
	RL []string `envconfig:"TIRE_RL_ADDRS"`
	RR []string `envconfig:"TIRE_RR_ADDRS"`
}

type Config struct {
	// HTTP
	Addr string `envconfig:"ADDR" default:"0.0.0.0:8080"`

	// I2C
	I2CDevice string `envconfig:"I2C_DEVICE" default:"/dev/i2c-1"`

	// Expander (SX1509)
	ExpanderAddress  uint8         `envconfig:"EXPANDER_ADDRESS" default:"0x20"`
	ExpanderInterval time.Duration `envconfig:"EXPANDER_INTERVAL" default:"2ms"`

	// Expander bit assignments
	BitKnobCenter uint `envconfig:"BIT_KNOB_CENTER" default:"0"`
	BitKnobInner  uint `envconfig:"BIT_KNOB_INNER"  default:"1"` // and bit+1
	BitKnobOuter  uint `envconfig:"BIT_KNOB_OUTER"  default:"3"` // and bit+1
	// 5 unused
	BitLED uint `envconfig:"BIT_LED"         default:"6"`
	// 7 unused
	BitJoyCenter uint `envconfig:"BIT_JOY_CENTER"  default:"8"`
	BitJoyDown   uint `envconfig:"BIT_JOY_DOWN"    default:"9"`
	BitJoyUp     uint `envconfig:"BIT_JOY_UP"      default:"10"`
	BitJoyRight  uint `envconfig:"BIT_JOY_RIGHT"   default:"11"`
	BitJoyLeft   uint `envconfig:"BIT_JOY_LEFT"    default:"12"`
	BitJoyKnob   uint `envconfig:"BIT_JOY_KNOB"    default:"13"` // and bit+1
	// 15 unused

	// AirSensor (BME280)
	AirSensorAddress  uint8         `envconfig:"AIR_SENSOR_ADDRESS" default:"0x77"`
	AirSensorInterval time.Duration `envconfig:"AIR_SENSOR_INTERVAL" default:"1s"`

	// LightSensor (VEML6030)
	LightSensorAddress  uint8         `envconfig:"LIGHT_SENSOR_ADDRESS" default:"0x48"`
	LightSensorInterval time.Duration `envconfig:"LIGHT_SENSOR_INTERVAL" default:"1s"`

	// Screenshot / ping loop
	ScreenshotFPS int           `envconfig:"SCREENSHOT_FPS" default:"30"`
	PingInterval  time.Duration `envconfig:"PING_INTERVAL" default:"1s"`

	// OLED display
	OLEDSPIPort  string           `envconfig:"OLED_SPI_PORT"   default:"/dev/spidev0.0"`
	OLEDSPISpeed physic.Frequency `envconfig:"OLED_SPI_SPEED"  default:"2.40MHz"`
	OLEDGPIOChip string           `envconfig:"OLED_GPIO_CHIP"  default:"gpiochip0"`
	OLEDDCPin    int              `envconfig:"OLED_DC_PIN"     default:"5"`
	OLEDResetPin int              `envconfig:"OLED_RESET_PIN"  default:"6"`
	OLEDWidth    int              `envconfig:"OLED_WIDTH"      default:"256"`
	OLEDHeight   int              `envconfig:"OLED_HEIGHT"     default:"64"`
	OLEDFlip     bool             `envconfig:"OLED_FLIP"       default:"true"`

	// TPMS tire address mapping
	Tires TireAddresses
}

// defaultTireAddresses are the known sensor addresses for each wheel position.
// They are used when no TIRE_*_ADDRS env vars are set.
var defaultTireAddresses = TireAddresses{
	FL: []string{"4a:a0:00:00:eb:02", "ae3806cb-ea50-2187-4d1d-10010147721a"},
	FR: []string{"4a:85:00:00:3a:50", "bc7ac313-2870-3c1f-c2bc-6047a80b58c2"},
	RL: []string{"4a:88:00:00:72:70", "24237bb2-4496-36b6-a755-64e9de75ac6c"},
	RR: []string{"4a:85:00:00:d7:38", "99633f0c-d627-5f15-7d5d-f171b5a745e7"},
}

// Load reads a .env file (if present) then populates Config from environment
// variables. Missing .env is silently ignored; malformed values are fatal.
func Load() *Config {
	if err := godotenv.Load(); err != nil {
		log.Println("config: no .env file found, using environment and defaults")
	}

	cfg := &Config{}
	if err := envconfig.Process("", cfg); err != nil {
		log.Fatal("config: ", err)
	}

	// Apply per-position defaults for any tire addresses not set via env.
	if len(cfg.Tires.FL) == 0 {
		cfg.Tires.FL = defaultTireAddresses.FL
	}
	if len(cfg.Tires.FR) == 0 {
		cfg.Tires.FR = defaultTireAddresses.FR
	}
	if len(cfg.Tires.RL) == 0 {
		cfg.Tires.RL = defaultTireAddresses.RL
	}
	if len(cfg.Tires.RR) == 0 {
		cfg.Tires.RR = defaultTireAddresses.RR
	}

	return cfg
}
