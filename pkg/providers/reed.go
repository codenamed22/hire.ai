package providers

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"hire.ai/pkg/models"
)

// ReedProvider implements the JobAPIProvider interface for Reed Jobs API
type ReedProvider struct {
	config APIConfig
	client *http.Client
}

// NewReedProvider creates a new Reed API provider
func NewReedProvider(config APIConfig, timeout time.Duration) *ReedProvider {
	return &ReedProvider{
		config: config,
		client: &http.Client{
			Timeout: timeout,
		},
	}
}

// GetName returns the provider name
func (p *ReedProvider) GetName() string {
	return "reed"
}

// Search searches for jobs using the Reed API
func (p *ReedProvider) Search(ctx context.Context, query SearchQuery) (*SearchResult, error) {
	if !p.IsConfigured() {
		return nil, fmt.Errorf("Reed provider not configured")
	}

	// Build the API URL
	apiURL, err := p.buildSearchURL(query)
	if err != nil {
		return nil, fmt.Errorf("failed to build search URL: %w", err)
	}

	// Create the request
	req, err := http.NewRequestWithContext(ctx, "GET", apiURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	// Add basic auth (Reed API uses API key as username)
	req.SetBasicAuth(p.config.APIKey, "")

	// Add headers
	req.Header.Set("Accept", "application/json")
	if userAgent, ok := p.config.Headers["User-Agent"]; ok {
		req.Header.Set("User-Agent", userAgent)
	}

	// Execute the request
	resp, err := p.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, &APIError{
			Provider:   p.GetName(),
			StatusCode: resp.StatusCode,
			Message:    fmt.Sprintf("API request failed with status %d", resp.StatusCode),
			Retryable:  resp.StatusCode >= 500,
		}
	}

	// Parse the response
	var apiResp ReedResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	// Convert to our standard format
	jobs := p.convertJobs(apiResp.Results)

	return &SearchResult{
		Jobs:       jobs,
		Total:      apiResp.TotalResults,
		Page:       query.Offset/query.Limit + 1,
		PerPage:    query.Limit,
		HasMore:    len(jobs) == query.Limit && apiResp.TotalResults > query.Offset+query.Limit,
		Provider:   p.GetName(),
		SearchedAt: time.Now(),
	}, nil
}

// IsConfigured checks if the provider is properly configured
func (p *ReedProvider) IsConfigured() bool {
	return p.config.Enabled && p.config.APIKey != ""
}

// GetRateLimit returns the rate limit information
func (p *ReedProvider) GetRateLimit() RateLimit {
	// Parse the cooldown period from string to duration
	cooldown, err := time.ParseDuration(p.config.RateLimit.CooldownPeriod)
	if err != nil {
		cooldown = 1 * time.Second // default
	}

	return RateLimit{
		RequestsPerMinute: p.config.RateLimit.RequestsPerMinute,
		RequestsPerHour:   p.config.RateLimit.RequestsPerHour,
		RequestsPerDay:    p.config.RateLimit.RequestsPerDay,
		CooldownPeriod:    cooldown,
	}
}

// ValidateCredentials validates the API credentials
func (p *ReedProvider) ValidateCredentials(ctx context.Context) error {
	// Test with a simple search
	testQuery := SearchQuery{
		Keywords: []string{"software"},
		Location: "London",
		Limit:    1,
		Offset:   0,
	}

	_, err := p.Search(ctx, testQuery)
	return err
}

// buildSearchURL builds the search URL with parameters
func (p *ReedProvider) buildSearchURL(query SearchQuery) (string, error) {
	baseURL := p.config.BaseURL
	if baseURL == "" {
		baseURL = "https://www.reed.co.uk/api/1.0/search"
	}

	u, err := url.Parse(baseURL)
	if err != nil {
		return "", err
	}

	params := url.Values{}

	// Add keywords
	if len(query.Keywords) > 0 {
		params.Set("keywords", strings.Join(query.Keywords, " "))
	}

	// Add location
	if query.Location != "" {
		params.Set("locationName", query.Location)
	}

	// Add remote work option
	if query.Remote {
		params.Set("remote", "true")
	}

	// Add salary range
	if query.Salary != nil {
		if query.Salary.Min > 0 {
			params.Set("minimumSalary", strconv.Itoa(query.Salary.Min))
		}
		if query.Salary.Max > 0 {
			params.Set("maximumSalary", strconv.Itoa(query.Salary.Max))
		}
	}

	// Add job type
	if query.JobType != "" {
		switch strings.ToLower(query.JobType) {
		case "full-time":
			params.Set("fullTime", "true")
		case "part-time":
			params.Set("partTime", "true")
		case "contract":
			params.Set("contract", "true")
		case "temporary":
			params.Set("temp", "true")
		}
	}

	// Add pagination
	params.Set("resultsToTake", strconv.Itoa(query.Limit))
	if query.Offset > 0 {
		params.Set("resultsToSkip", strconv.Itoa(query.Offset))
	}

	// Add date posted filter
	if query.DatePosted != "" {
		days := parseDatePosted(query.DatePosted)
		if days > 0 {
			params.Set("postedByDays", strconv.Itoa(days))
		}
	}

	u.RawQuery = params.Encode()
	return u.String(), nil
}

// convertJobs converts Reed API response to our standard Job format
func (p *ReedProvider) convertJobs(results []ReedJob) []models.Job {
	var jobs []models.Job

	for _, reedJob := range results {
		job := models.Job{
			ID:          fmt.Sprintf("reed_%d", reedJob.JobID),
			Title:       reedJob.JobTitle,
			Company:     reedJob.EmployerName,
			Location:    reedJob.LocationName,
			Description: reedJob.JobDescription,
			Source:      "Reed",
			Link:        reedJob.JobURL,
			ScrapedAt:   time.Now(),
			Salary:      p.formatSalary(reedJob),
		}

		// Parse date
		if reedJob.Date != "" {
			if parsed, err := time.Parse("02/01/2006", reedJob.Date); err == nil {
				job.ScrapedAt = parsed
			}
		}

		// Add keywords from the job title and description
		job.Keywords = extractKeywords(job.Title, job.Description)

		jobs = append(jobs, job)
	}

	return jobs
}

// formatSalary formats salary information from Reed job
func (p *ReedProvider) formatSalary(job ReedJob) string {
	if job.MinimumSalary > 0 && job.MaximumSalary > 0 {
		return fmt.Sprintf("£%.0f - £%.0f per year", job.MinimumSalary, job.MaximumSalary)
	}
	if job.MinimumSalary > 0 {
		return fmt.Sprintf("£%.0f+ per year", job.MinimumSalary)
	}
	return ""
}

// Reed API response structures
type ReedResponse struct {
	Results      []ReedJob `json:"results"`
	TotalResults int       `json:"totalResults"`
}

type ReedJob struct {
	JobID           int     `json:"jobId"`
	EmployerID      int     `json:"employerId"`
	EmployerName    string  `json:"employerName"`
	EmployerProfile string  `json:"employerProfile"`
	JobTitle        string  `json:"jobTitle"`
	LocationName    string  `json:"locationName"`
	MinimumSalary   float64 `json:"minimumSalary"`
	MaximumSalary   float64 `json:"maximumSalary"`
	Currency        string  `json:"currency"`
	ExpirationDate  string  `json:"expirationDate"`
	Date            string  `json:"date"`
	JobDescription  string  `json:"jobDescription"`
	JobURL          string  `json:"jobUrl"`
	Applications    int     `json:"applications"`
	JobType         string  `json:"jobType"`
}
