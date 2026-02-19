# VelociPi

## About

This runs on a Raspberry Pi 5 to control the screens, cameras, joysticks, audio, and various other toys in my Velocity V-Twin-6 N711ME. I don't know why you're here, but good luck.

## Dev

`npm run dev`

## Build

`npm run build`

## Configuration

Configuration is read from environment variables. A `.env` file in the working directory is loaded automatically if present.

| Env var                 | Default          | Description                                                  |
| ----------------------- | ---------------- | ------------------------------------------------------------ |
| `ADDR`                  | `0.0.0.0:8080`   | HTTP listen address                                          |
| `I2C_DEVICE`            | `/dev/i2c-1`     | I2C bus device used by all sensors                           |
| `AIR_SENSOR_ADDRESS`    | `0x77`           | I2C address of the BME280 air sensor                         |
| `AIR_SENSOR_INTERVAL`   | `1s`             | How often to poll the air sensor                             |
| `LIGHT_SENSOR_ADDRESS`  | `0x48`           | I2C address of the VEML6030 light sensor                     |
| `LIGHT_SENSOR_INTERVAL` | `1s`             | How often to poll the light sensor                           |
| `SCREENSHOT_FPS`        | `30`             | Screenshot capture rate (frames per second)                  |
| `PING_INTERVAL`         | `1s`             | WebSocket ping interval                                      |
| `OLED_SPI_PORT`         | `/dev/spidev0.0` | SPI device for the OLED display                              |
| `OLED_SPI_SPEED`        | `10MHz`          | SPI clock frequency (e.g. `10MHz`, `5MHz`)                   |
| `OLED_GPIO_CHIP`        | `gpiochip0`      | GPIO chip device                                             |
| `OLED_DC_PIN`           | `24`             | BCM GPIO pin number for data/command (DC)                    |
| `OLED_RESET_PIN`        | `25`             | BCM GPIO pin number for reset                                |
| `OLED_WIDTH`            | `256`            | Display width in pixels                                      |
| `OLED_HEIGHT`           | `64`             | Display height in pixels                                     |
| `OLED_FLIP`             | `false`          | Flip the frame buffer 180°                                   |
| `TIRE_FL_ADDRS`         | _(see below)_    | Comma-separated BT addresses for the front-left TPMS sensor  |
| `TIRE_FR_ADDRS`         | _(see below)_    | Comma-separated BT addresses for the front-right TPMS sensor |
| `TIRE_RL_ADDRS`         | _(see below)_    | Comma-separated BT addresses for the rear-left TPMS sensor   |
| `TIRE_RR_ADDRS`         | _(see below)_    | Comma-separated BT addresses for the rear-right TPMS sensor  |

### Default TPMS addresses

Each sensor can advertise under multiple Bluetooth addresses. The defaults match the sensors paired with this vehicle. (Linux and macOS have different ideas of what to use as an address)

| Position | Addresses                                                   |
| -------- | ----------------------------------------------------------- |
| FL       | `4a:a0:00:00:eb:02`, `ae3806cb-ea50-2187-4d1d-10010147721a` |
| FR       | `4a:85:00:00:3a:50`, `bc7ac313-2870-3c1f-c2bc-6047a80b58c2` |
| RL       | `4a:88:00:00:72:70`, `24237bb2-4496-36b6-a755-64e9de75ac6c` |
| RR       | `4a:85:00:00:d7:38`, `99633f0c-d627-5f15-7d5d-f171b5a745e7` |

To override a position, set the corresponding env var to a comma-separated list of addresses:

```
TIRE_FL_ADDRS=aa:bb:cc:dd:ee:ff,some-uuid-here
```
