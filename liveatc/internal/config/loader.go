// Package config loads liveatc configuration using the same layered scheme as
// the parent velocipi project: a required defaults file is read first, then an
// optional override file is unmarshalled on top of a copy of the defaults so
// only the keys present in the override are changed.
package config

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// Layered holds both the effective (merged) config and the untouched defaults.
// Keeping the defaults around lets callers diff against them later (e.g. to
// persist only overrides), mirroring config.LoadResult in the parent project.
type Layered[T any] struct {
	Effective *T // defaults + overrides
	Defaults  *T // defaults file only
}

// LoadLayered reads defaultPath (required) as the baseline, then overlays
// overridePath (optional) on top. It is intentionally generic so the same
// merge logic can be reused for any config struct.
//
// A missing override file is not an error -- the defaults are returned as-is.
// A malformed override file IS an error here (the parent project chooses to log
// and continue; a standalone service is better off failing loudly at startup).
func LoadLayered[T any](defaultPath, overridePath string) (*Layered[T], error) {
	var defaults T

	data, err := os.ReadFile(defaultPath)
	if err != nil {
		return nil, fmt.Errorf("read defaults %q: %w", defaultPath, err)
	}
	if err := yaml.Unmarshal(data, &defaults); err != nil {
		return nil, fmt.Errorf("parse defaults %q: %w", defaultPath, err)
	}

	// Start from a copy of the defaults, then layer the override on top. yaml.v3
	// only writes fields that are present in the override document, leaving the
	// rest of the copy at its default value.
	effective := defaults
	if ov, err := os.ReadFile(overridePath); err == nil {
		if err := yaml.Unmarshal(ov, &effective); err != nil {
			return nil, fmt.Errorf("parse override %q: %w", overridePath, err)
		}
	} else if !os.IsNotExist(err) {
		return nil, fmt.Errorf("read override %q: %w", overridePath, err)
	}

	return &Layered[T]{Effective: &effective, Defaults: &defaults}, nil
}
