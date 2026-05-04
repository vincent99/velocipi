package thermalcam

// ShutterMode controls automatic shutter (flat-field) calibration.
type ShutterMode byte

const (
	ShutterOff       ShutterMode = 0x00
	ShutterTiming    ShutterMode = 0x01
	ShutterTempDelta ShutterMode = 0x02
	ShutterFullAuto  ShutterMode = 0x03
)

func (m ShutterMode) String() string {
	switch m {
	case ShutterOff:
		return "off"
	case ShutterTiming:
		return "timing"
	case ShutterTempDelta:
		return "temp-delta"
	case ShutterFullAuto:
		return "full-auto"
	default:
		return "unknown"
	}
}

// Palette is the false-color mapping applied to the thermal image.
type Palette byte

const (
	PaletteWhiteHot  Palette = 0x00
	PaletteBlackHot  Palette = 0x01
	PaletteFusion1   Palette = 0x02
	PaletteRainbow   Palette = 0x03
	PaletteFusion2   Palette = 0x04
	PaletteIronRed1  Palette = 0x05
	PaletteIronRed2  Palette = 0x06
	PaletteDarkBrown Palette = 0x07
	PaletteColor1    Palette = 0x08
	PaletteColor2    Palette = 0x09
	PaletteIceFire   Palette = 0x0A
	PaletteRain      Palette = 0x0B
	PaletteGreenHot  Palette = 0x0C
	PaletteRedHot    Palette = 0x0D
	PaletteDeepBlue  Palette = 0x0E
)

func (p Palette) String() string {
	switch p {
	case PaletteWhiteHot:
		return "white-hot"
	case PaletteBlackHot:
		return "black-hot"
	case PaletteFusion1:
		return "fusion-1"
	case PaletteRainbow:
		return "rainbow"
	case PaletteFusion2:
		return "fusion-2"
	case PaletteIronRed1:
		return "iron-red-1"
	case PaletteIronRed2:
		return "iron-red-2"
	case PaletteDarkBrown:
		return "dark-brown"
	case PaletteColor1:
		return "color-1"
	case PaletteColor2:
		return "color-2"
	case PaletteIceFire:
		return "ice-fire"
	case PaletteRain:
		return "rain"
	case PaletteGreenHot:
		return "green-hot"
	case PaletteRedHot:
		return "red-hot"
	case PaletteDeepBlue:
		return "deep-blue"
	default:
		return "unknown"
	}
}

// MirrorMode controls image mirroring.
type MirrorMode byte

const (
	MirrorNone      MirrorMode = 0x00
	MirrorCenter    MirrorMode = 0x01
	MirrorLeftRight MirrorMode = 0x02
	MirrorUpDown    MirrorMode = 0x03
)

func (m MirrorMode) String() string {
	switch m {
	case MirrorNone:
		return "none"
	case MirrorCenter:
		return "center"
	case MirrorLeftRight:
		return "left-right"
	case MirrorUpDown:
		return "up-down"
	default:
		return "unknown"
	}
}

// CursorDir is used for defective-pixel correction cursor movement.
type CursorDir byte

const (
	CursorUp     CursorDir = 0x02
	CursorDown   CursorDir = 0x03
	CursorLeft   CursorDir = 0x04
	CursorRight  CursorDir = 0x05
	CursorCenter CursorDir = 0x06
)

// State holds a snapshot of all readable camera parameters.
type State struct {
	Model               string `json:"model"`
	FPGAVersion         string `json:"fpgaVersion"`
	FPGACompileTime     string `json:"fpgaCompileTime"`
	SoftwareVersion     string `json:"swVersion"`
	SoftwareCompileTime string `json:"swCompileTime"`
	CalibrationDate     string `json:"calibrationDate"`
	ISPVersion          uint32 `json:"ispVersion"`
	ShutterMode         string `json:"shutterMode"`
	ShutterIntervalMin  uint16 `json:"shutterIntervalMin"`
	Brightness          uint8  `json:"brightness"`
	Contrast            uint8  `json:"contrast"`
	DetailEnhancement   uint8  `json:"detailEnhancement"`
	StaticDenoising     uint8  `json:"staticDenoising"`
	DynamicDenoising    uint8  `json:"dynamicDenoising"`
	Palette             string `json:"palette"`
	Mirroring           string `json:"mirroring"`
}
