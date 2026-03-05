package siyi

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"time"
)

// MediaFile represents a photo or video file on the camera's SD card.
type MediaFile struct {
	Name string `json:"name"`
	URL  string `json:"url"`
}

// Downloader fetches photo and video files from the Siyi camera's HTTP API
// running on port 82.
type Downloader struct {
	host    string
	destDir string
	client  *http.Client
}

// NewDownloader creates a Downloader that saves files to destDir.
func NewDownloader(host, destDir string) *Downloader {
	return &Downloader{
		host:    host,
		destDir: destDir,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

type dirResponse struct {
	Success bool `json:"success"`
	Data    struct {
		Directories []struct {
			Path string `json:"path"`
		} `json:"directories"`
	} `json:"data"`
}

type listResponse struct {
	Success bool `json:"success"`
	Data    struct {
		List []struct {
			Name string `json:"name"`
			URL  string `json:"url"`
		} `json:"list"`
	} `json:"data"`
}

// ListPhotos returns all photo files on the SD card.
func (d *Downloader) ListPhotos(ctx context.Context) ([]MediaFile, error) {
	return d.listMedia(ctx, 0)
}

// ListVideos returns all video files on the SD card.
func (d *Downloader) ListVideos(ctx context.Context) ([]MediaFile, error) {
	return d.listMedia(ctx, 1)
}

func (d *Downloader) listMedia(ctx context.Context, mediaType int) ([]MediaFile, error) {
	base := fmt.Sprintf("http://%s:%d", d.host, DownloadPort)

	// Step 1: get directories.
	dirURL := fmt.Sprintf("%s/cgi-bin/media.cgi/api/v1/getdirectories?media_type=%d", base, mediaType)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, dirURL, nil)
	if err != nil {
		return nil, err
	}
	resp, err := d.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var dirs dirResponse
	if err := json.NewDecoder(resp.Body).Decode(&dirs); err != nil {
		return nil, fmt.Errorf("siyi downloader: decode directories: %w", err)
	}
	if !dirs.Success {
		return nil, fmt.Errorf("siyi downloader: getdirectories failed")
	}

	var files []MediaFile
	for _, dir := range dirs.Data.Directories {
		listURL := fmt.Sprintf(
			"%s/cgi-bin/media.cgi/api/v1/getmedialist?media_type=%d&path=%s&start=0&count=9999",
			base, mediaType, url.QueryEscape(dir.Path),
		)
		req2, err := http.NewRequestWithContext(ctx, http.MethodGet, listURL, nil)
		if err != nil {
			return nil, err
		}
		resp2, err := d.client.Do(req2)
		if err != nil {
			return nil, err
		}
		var lst listResponse
		err = json.NewDecoder(resp2.Body).Decode(&lst)
		resp2.Body.Close()
		if err != nil {
			return nil, fmt.Errorf("siyi downloader: decode medialist: %w", err)
		}
		for _, f := range lst.Data.List {
			// Ensure the URL points to the correct host (camera may embed its own IP).
			fixedURL := d.fixHost(f.URL)
			files = append(files, MediaFile{Name: f.Name, URL: fixedURL})
		}
	}
	return files, nil
}

// Download downloads a single MediaFile to destDir and returns the local path.
func (d *Downloader) Download(ctx context.Context, f MediaFile) (string, error) {
	if err := os.MkdirAll(d.destDir, 0o755); err != nil {
		return "", err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, f.URL, nil)
	if err != nil {
		return "", err
	}
	resp, err := d.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	dest := filepath.Join(d.destDir, f.Name)
	out, err := os.Create(dest)
	if err != nil {
		return "", err
	}
	defer out.Close()

	if _, err := io.Copy(out, resp.Body); err != nil {
		return "", err
	}
	return dest, nil
}

// fixHost replaces the host portion of a URL with d.host to handle cases where
// the camera embeds its own (possibly different) IP in file URLs.
func (d *Downloader) fixHost(rawURL string) string {
	u, err := url.Parse(rawURL)
	if err != nil {
		return rawURL
	}
	u.Host = fmt.Sprintf("%s:%d", d.host, DownloadPort)
	return u.String()
}
