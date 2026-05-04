//go:build !linux

package oled

import (
	"image"
	"log"
)

func NewSSD1327(_ Config, width, height int) (*SSD1327, error) {
	log.Println("OLED: Hardware unavailable, using stub")
	return &SSD1327{width: width, height: height}, nil
}
func NewGE256X64B(_ Config, width, height int) (*Noritake, error) {
	log.Println("OLED: Hardware unavailable, using stub")
	return &Noritake{width: width, height: height}, nil
}

// SSD1327 is a stub type for non-Linux builds.
type SSD1327 struct{ width, height int }

func (o *SSD1327) Blit(_ image.Image)   {}
func (o *SSD1327) SetBrightness(_ byte) {}
func (o *SSD1327) Width() int           { return o.width }
func (o *SSD1327) Height() int          { return o.height }
func (o *SSD1327) Close()               {}

// Noritake is a stub type for non-Linux builds.
type Noritake struct{ width, height int }

func (n *Noritake) Blit(_ image.Image)   {}
func (n *Noritake) SetBrightness(_ byte) {}
func (n *Noritake) Width() int           { return n.width }
func (n *Noritake) Height() int          { return n.height }
func (n *Noritake) Close()               {}
