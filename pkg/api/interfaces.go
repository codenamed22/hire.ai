package api

import (
	"context"
	"time"

	"hire.ai/pkg/models"
)

// JobAPIProvider defines the interface that all job API providers must implement
type JobAPIProvider interface {
	// GetName returns the provider name (e.g., "usajobs", "reed", "jsearch")
	GetName() string

	// Search searches for jobs using the API
	Search(ctx context.Context, query SearchQuery) (*SearchResult, error)

	// IsConfigured checks if the provider is properly configured with required credentials
	IsConfigured() bool

	// GetRateLimit returns the rate limit information
	GetRateLimit() RateLimit

	// ValidateCredentials validates the API credentials
	ValidateCredentials(ctx context.Context) error
}

// SearchQuery represents a job search query
type SearchQuery struct {
	Keywords   []string `json:"keywords"`
	Location   string   `json:"location"`
	Remote     bool     `json:"remote"`
	Salary     *Salary  `json:"salary,omitempty"`
	Experience string   `json:"experience,omitempty"`
	JobType    string   `json:"job_type,omitempty"` // full-time, part-time, contract
	Company    string   `json:"company,omitempty"`
	DatePosted string   `json:"date_posted,omitempty"` // 1d, 3d, 7d, 14d, 30d
	Limit      int      `json:"limit"`
	Offset     int      `json:"offset"`
}

// Salary represents salary range for job search
type Salary struct {
	Min      int    `json:"min"`
	Max      int    `json:"max"`
	Currency string `json:"currency"`
	Period   string `json:"period"` // yearly, monthly, hourly
}

// SearchResult represents the result of a job search
type SearchResult struct {
	Jobs       []models.Job `json:"jobs"`
	Total      int          `json:"total"`
	Page       int          `json:"page"`
	PerPage    int          `json:"per_page"`
	HasMore    bool         `json:"has_more"`
	Provider   string       `json:"provider"`
	SearchedAt time.Time    `json:"searched_at"`
}

// RateLimit represents API rate limiting information
type RateLimit struct {
	RequestsPerMinute int           `json:"requests_per_minute"`
	RequestsPerHour   int           `json:"requests_per_hour"`
	RequestsPerDay    int           `json:"requests_per_day"`
	CooldownPeriod    time.Duration `json:"-"` // Internal use only
}

// RateLimitConfig represents rate limit configuration in JSON
type RateLimitConfig struct {
	RequestsPerMinute int    `json:"requests_per_minute"`
	RequestsPerHour   int    `json:"requests_per_hour"`
	RequestsPerDay    int    `json:"requests_per_day"`
	CooldownPeriod    string `json:"cooldown_period"` // Duration string like "2s"
}

// APIConfig represents configuration for an API provider
type APIConfig struct {
	Name        string            `json:"name"`
	Enabled     bool              `json:"enabled"`
	Provider    string            `json:"provider"` // usajobs, reed, jsearch, etc.
	BaseURL     string            `json:"base_url"`
	APIKey      string            `json:"api_key"`
	SecretKey   string            `json:"secret_key,omitempty"`
	RateLimit   RateLimitConfig   `json:"rate_limit"`
	MaxResults  int               `json:"max_results"`
	Timeout     string            `json:"timeout"` // Duration string like "30s"
	RetryConfig RetryConfig       `json:"retry_config"`
	Headers     map[string]string `json:"headers,omitempty"`
	Params      map[string]string `json:"params,omitempty"`
}

// RetryConfig represents retry configuration for API calls
type RetryConfig struct {
	MaxAttempts int     `json:"max_attempts"`
	InitialWait string  `json:"initial_wait"` // Duration string like "1s"
	MaxWait     string  `json:"max_wait"`     // Duration string like "10s"
	Multiplier  float64 `json:"multiplier"`
}

// APIError represents an error from an API provider
type APIError struct {
	Provider   string `json:"provider"`
	StatusCode int    `json:"status_code"`
	Message    string `json:"message"`
	Details    string `json:"details,omitempty"`
	Retryable  bool   `json:"retryable"`
}

func (e *APIError) Error() string {
	return e.Message
}

// APIStats represents statistics for API usage
type APIStats struct {
	Provider        string        `json:"provider"`
	TotalRequests   int           `json:"total_requests"`
	SuccessRequests int           `json:"success_requests"`
	FailedRequests  int           `json:"failed_requests"`
	TotalJobs       int           `json:"total_jobs"`
	AverageLatency  time.Duration `json:"average_latency"`
	LastUsed        time.Time     `json:"last_used"`
}
