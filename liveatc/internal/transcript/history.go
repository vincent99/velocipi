package transcript

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
)

// ReadJSONL parses a transcript JSONL file into records, in file order. Blank
// lines and individually malformed lines are skipped rather than failing the
// whole read (the log is append-only and a torn final line shouldn't hide the
// rest). A missing file returns an empty slice, not an error.
func ReadJSONL(path string) ([]TransmissionRecord, error) {
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer f.Close()

	var recs []TransmissionRecord
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 64*1024), 4*1024*1024) // records can be large
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var r TransmissionRecord
		if err := json.Unmarshal(line, &r); err != nil {
			continue
		}
		recs = append(recs, r)
	}
	return recs, sc.Err()
}

// applyTo finds the record with the given id, applies mut to it in place, and
// returns the updated record and whether it was found.
func applyTo(recs []TransmissionRecord, id string, mut func(*TransmissionRecord)) (TransmissionRecord, bool) {
	for i := range recs {
		if recs[i].ID == id {
			mut(&recs[i])
			return recs[i], true
		}
	}
	return TransmissionRecord{}, false
}

// writeJSONLAtomic writes records to path via a temp file + rename so a reader
// (or a crash) never sees a half-written log.
func writeJSONLAtomic(path string, recs []TransmissionRecord) error {
	tmp, err := os.CreateTemp(filepath.Dir(path), ".transcript-*.tmp")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName) // no-op after a successful rename

	w := bufio.NewWriter(tmp)
	for _, r := range recs {
		line, err := json.Marshal(r)
		if err != nil {
			tmp.Close()
			return err
		}
		if _, err := w.Write(append(line, '\n')); err != nil {
			tmp.Close()
			return err
		}
	}
	if err := w.Flush(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmpName, path)
}

// UpdateRecordFile rewrites the JSONL at path, applying mut to the record with
// id. Use this only for files NOT owned by an open Writer (i.e. past sessions);
// for the live session route the update through Writer.UpdateRecord so it can't
// race the appender. Returns the updated record and whether it was found.
func UpdateRecordFile(path, id string, mut func(*TransmissionRecord)) (TransmissionRecord, bool, error) {
	recs, err := ReadJSONL(path)
	if err != nil {
		return TransmissionRecord{}, false, err
	}
	rec, ok := applyTo(recs, id, mut)
	if !ok {
		return TransmissionRecord{}, false, nil
	}
	if err := writeJSONLAtomic(path, recs); err != nil {
		return TransmissionRecord{}, false, err
	}
	return rec, true, nil
}
