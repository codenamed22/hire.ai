package storage_test

import (
    "encoding/json"
    "os"
    "path/filepath"
    "strings"
    "sync"

    "hire.ai/pkg/models"
)

// Storage interface matches what main.go expects
type Storage interface {
    Store(jobs []models.Job) error
    Search(filter models.JobFilter) (models.JobSearchResult, error)
    GetStats() (*models.JobStats, error)
    GetAll() ([]models.Job, error)
    Close() error
}

type FileStorage struct {
    filePath string
    mu       sync.Mutex
    jobs     []models.Job
}

// NewFileStorage returns a Storage and error
func NewFileStorage(filePath string) (Storage, error) {
    fs := &FileStorage{filePath: filePath}
    if err := fs.load(); err != nil && !os.IsNotExist(err) {
        return nil, err
    }
    return fs, nil
}

// Store appends jobs and saves to disk
func (fs *FileStorage) Store(jobs []models.Job) error {
    fs.mu.Lock()
    defer fs.mu.Unlock()
    fs.jobs = append(fs.jobs, jobs...)
    return fs.save()
}

// Search filters jobs based on JobFilter fields
func (fs *FileStorage) Search(filter models.JobFilter) (models.JobSearchResult, error) {
    fs.mu.Lock()
    defer fs.mu.Unlock()

    var results []models.Job
    for _, job := range fs.jobs {
        if matchJobFilter(job, filter) {
            results = append(results, job)
        }
    }

    return models.JobSearchResult{
        Jobs:  results,
        Total: len(results),
    }, nil
}

// GetStats calculates and returns stats
func (fs *FileStorage) GetStats() (*models.JobStats, error) {
    fs.mu.Lock()
    defer fs.mu.Unlock()
    return &models.JobStats{
        TotalJobs: len(fs.jobs),
    }, nil
}

// GetAll returns all jobs
func (fs *FileStorage) GetAll() ([]models.Job, error) {
    fs.mu.Lock()
    defer fs.mu.Unlock()
    return append([]models.Job(nil), fs.jobs...), nil
}

// Close saves jobs to file
func (fs *FileStorage) Close() error {
    return fs.save()
}

// internal: load from disk
func (fs *FileStorage) load() error {
    data, err := os.ReadFile(fs.filePath)
    if err != nil {
        return err
    }
    return json.Unmarshal(data, &fs.jobs)
}

// internal: save to disk
func (fs *FileStorage) save() error {
    if err := os.MkdirAll(filepath.Dir(fs.filePath), 0755); err != nil {
        return err
    }
    data, err := json.MarshalIndent(fs.jobs, "", "  ")
    if err != nil {
        return err
    }
    return os.WriteFile(fs.filePath, data, 0644)
}

// matchJobFilter does a simple text match for filter fields
func matchJobFilter(job models.Job, filter models.JobFilter) bool {
    // Keywords filter
    if len(filter.Keywords) > 0 {
        found := false
        for _, kw := range filter.Keywords {
            if strings.Contains(strings.ToLower(job.Title), strings.ToLower(kw)) ||
                strings.Contains(strings.ToLower(job.Description), strings.ToLower(kw)) {
                found = true
                break
            }
        }
        if !found {
            return false
        }
    }

    // Location filter
    if filter.Location != "" && !strings.Contains(strings.ToLower(job.Location), strings.ToLower(filter.Location)) {
        return false
    }

    // Sources filter
    if len(filter.Sources) > 0 {
        found := false
        for _, src := range filter.Sources {
            if strings.EqualFold(job.Source, src) {
                found = true
                break
            }
        }
        if !found {
            return false
        }
    }

    // Salary range filter
    min, max := job.GetSalaryRange()
    if filter.MinSalary > 0 && max < filter.MinSalary {
        return false
    }
    if filter.MaxSalary > 0 && min > filter.MaxSalary {
        return false
    }

    // Date range filter
    if !filter.DateFrom.IsZero() && job.ScrapedAt.Before(filter.DateFrom) {
        return false
    }
    if !filter.DateTo.IsZero() && job.ScrapedAt.After(filter.DateTo) {
        return false
    }

    // IsActive filter
    if filter.IsActive != nil && job.IsActive != *filter.IsActive {
        return false
    }

    return true
}