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

// JSearchProvider implements the JobAPIProvider interface for JSearch API (RapidAPI)
type JSearchProvider struct {
	config APIConfig
	client *http.Client
}

// NewJSearchProvider creates a new JSearch API provider
func NewJSearchProvider(config APIConfig, timeout time.Duration) *JSearchProvider {
	return &JSearchProvider{
		config: config,
		client: &http.Client{
			Timeout: timeout,
		},
	}
}

// GetName returns the provider name
func (p *JSearchProvider) GetName() string {
	return "jsearch"
}

// Search searches for jobs using the JSearch API
func (p *JSearchProvider) Search(ctx context.Context, query SearchQuery) (*SearchResult, error) {
	if !p.IsConfigured() {
		return nil, fmt.Errorf("JSearch provider not configured")
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

	// Add RapidAPI headers
	req.Header.Set("X-RapidAPI-Key", p.config.APIKey)
	req.Header.Set("X-RapidAPI-Host", "jsearch.p.rapidapi.com")
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
	var apiResp JSearchResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	if apiResp.Status != "OK" {
		return nil, &APIError{
			Provider: p.GetName(),
			Message:  fmt.Sprintf("API returned error: %s", apiResp.Status),
		}
	}

	// Convert to our standard format
	jobs := p.convertJobs(apiResp.Data)

	return &SearchResult{
		Jobs:       jobs,
		Total:      len(jobs),
		Page:       query.Offset/query.Limit + 1,
		PerPage:    query.Limit,
		HasMore:    len(jobs) == query.Limit,
		Provider:   p.GetName(),
		SearchedAt: time.Now(),
	}, nil
}

// IsConfigured checks if the provider is properly configured
func (p *JSearchProvider) IsConfigured() bool {
	return p.config.Enabled && p.config.APIKey != ""
}

// GetRateLimit returns the rate limit information
func (p *JSearchProvider) GetRateLimit() RateLimit {
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
func (p *JSearchProvider) ValidateCredentials(ctx context.Context) error {
	// Test with a simple search
	testQuery := SearchQuery{
		Keywords: []string{"software engineer"},
		Location: "New York",
		Limit:    1,
		Offset:   0,
	}

	_, err := p.Search(ctx, testQuery)
	return err
}

// buildSearchURL builds the search URL with parameters
func (p *JSearchProvider) buildSearchURL(query SearchQuery) (string, error) {
	baseURL := p.config.BaseURL
	if baseURL == "" {
		baseURL = "https://jsearch.p.rapidapi.com/search"
	}

	u, err := url.Parse(baseURL)
	if err != nil {
		return "", err
	}

	params := url.Values{}

	// Build query string
	var queryParts []string
	if len(query.Keywords) > 0 {
		queryParts = append(queryParts, strings.Join(query.Keywords, " "))
	}
	if query.Location != "" {
		queryParts = append(queryParts, "in "+query.Location)
	}

	if len(queryParts) > 0 {
		params.Set("query", strings.Join(queryParts, " "))
	}

	// Add pagination
	params.Set("num_pages", "1")
	params.Set("page", strconv.Itoa(query.Offset/query.Limit+1))

	// Add remote work option
	if query.Remote {
		params.Set("remote_jobs_only", "true")
	}

	// Add job type
	if query.JobType != "" {
		switch strings.ToLower(query.JobType) {
		case "full-time":
			params.Set("employment_types", "FULLTIME")
		case "part-time":
			params.Set("employment_types", "PARTTIME")
		case "contract":
			params.Set("employment_types", "CONTRACTOR")
		case "intern":
			params.Set("employment_types", "INTERN")
		}
	}

	// Add date posted filter
	if query.DatePosted != "" {
		switch strings.ToLower(query.DatePosted) {
		case "1d", "today":
			params.Set("date_posted", "today")
		case "3d":
			params.Set("date_posted", "3days")
		case "7d", "week":
			params.Set("date_posted", "week")
		case "30d", "month":
			params.Set("date_posted", "month")
		}
	}

	u.RawQuery = params.Encode()
	return u.String(), nil
}

// convertJobs converts JSearch API response to our standard Job format
func (p *JSearchProvider) convertJobs(data []JSearchJob) []models.Job {
	var jobs []models.Job

	for _, jsJob := range data {
		job := models.Job{
			ID:          fmt.Sprintf("jsearch_%s", jsJob.JobID),
			Title:       jsJob.JobTitle,
			Company:     jsJob.EmployerName,
			Location:    p.formatLocation(jsJob),
			Description: jsJob.JobDescription,
			Source:      "JSearch",
			Link:        jsJob.JobApplyLink,
			ScrapedAt:   time.Now(),
			Salary:      p.formatSalary(jsJob),
		}

		// Parse date
		if jsJob.JobPostedAtDatetimeUTC != "" {
			if parsed, err := time.Parse(time.RFC3339, jsJob.JobPostedAtDatetimeUTC); err == nil {
				job.ScrapedAt = parsed
			}
		}

		// Add employment type info
		if jsJob.JobEmploymentType != "" {
			job.Description = fmt.Sprintf("[%s] %s", jsJob.JobEmploymentType, job.Description)
		}

		// Add keywords from the job title and description
		job.Keywords = extractKeywords(job.Title, job.Description)

		jobs = append(jobs, job)
	}

	return jobs
}

// formatLocation formats location from JSearch job data
func (p *JSearchProvider) formatLocation(job JSearchJob) string {
	location := job.JobCity
	if job.JobState != "" {
		if location != "" {
			location += ", " + job.JobState
		} else {
			location = job.JobState
		}
	}
	if job.JobCountry != "" {
		if location != "" {
			location += ", " + job.JobCountry
		} else {
			location = job.JobCountry
		}
	}
	if location == "" {
		location = "Not specified"
	}
	return location
}

// formatSalary formats salary information from JSearch job
func (p *JSearchProvider) formatSalary(job JSearchJob) string {
	if job.JobMinSalary != nil && job.JobMaxSalary != nil {
		period := "per year"
		if job.JobSalaryPeriod != "" {
			period = "per " + job.JobSalaryPeriod
		}
		currency := "$"
		if job.JobSalaryCurrency != "" {
			currency = job.JobSalaryCurrency + " "
		}
		return fmt.Sprintf("%s%.0f - %s%.0f %s", currency, *job.JobMinSalary, currency, *job.JobMaxSalary, period)
	}
	if job.JobMinSalary != nil {
		period := "per year"
		if job.JobSalaryPeriod != "" {
			period = "per " + job.JobSalaryPeriod
		}
		currency := "$"
		if job.JobSalaryCurrency != "" {
			currency = job.JobSalaryCurrency + " "
		}
		return fmt.Sprintf("%s%.0f+ %s", currency, *job.JobMinSalary, period)
	}
	return ""
}

// JSearch API response structures
type JSearchResponse struct {
	Status     string       `json:"status"`
	RequestID  string       `json:"request_id"`
	Parameters interface{}  `json:"parameters"`
	Data       []JSearchJob `json:"data"`
}

type JSearchJob struct {
	JobID                       string                 `json:"job_id"`
	EmployerName                string                 `json:"employer_name"`
	EmployerLogo                *string                `json:"employer_logo"`
	EmployerWebsite             *string                `json:"employer_website"`
	EmployerCompanyType         *string                `json:"employer_company_type"`
	JobPublisher                string                 `json:"job_publisher"`
	JobEmploymentType           string                 `json:"job_employment_type"`
	JobTitle                    string                 `json:"job_title"`
	JobApplyLink                string                 `json:"job_apply_link"`
	JobApplyIsDirect            bool                   `json:"job_apply_is_direct"`
	JobApplyQualityScore        float64                `json:"job_apply_quality_score"`
	JobDescription              string                 `json:"job_description"`
	JobIsRemote                 bool                   `json:"job_is_remote"`
	JobPostedAtTimestamp        int64                  `json:"job_posted_at_timestamp"`
	JobPostedAtDatetimeUTC      string                 `json:"job_posted_at_datetime_utc"`
	JobCity                     string                 `json:"job_city"`
	JobState                    string                 `json:"job_state"`
	JobCountry                  string                 `json:"job_country"`
	JobLatitude                 *float64               `json:"job_latitude"`
	JobLongitude                *float64               `json:"job_longitude"`
	JobBenefits                 []string               `json:"job_benefits"`
	JobGoogleLink               string                 `json:"job_google_link"`
	JobOfferExpirationDatetime  *string                `json:"job_offer_expiration_datetime_utc"`
	JobOfferExpirationTimestamp *int64                 `json:"job_offer_expiration_timestamp"`
	JobRequiredExperience       map[string]interface{} `json:"job_required_experience"`
	JobRequiredSkills           []string               `json:"job_required_skills"`
	JobRequiredEducation        map[string]interface{} `json:"job_required_education"`
	JobExperienceInPlace        bool                   `json:"job_experience_in_place_of_education"`
	JobMinSalary                *float64               `json:"job_min_salary"`
	JobMaxSalary                *float64               `json:"job_max_salary"`
	JobSalaryCurrency           string                 `json:"job_salary_currency"`
	JobSalaryPeriod             string                 `json:"job_salary_period"`
	JobHighlights               map[string][]string    `json:"job_highlights"`
	JobJobTitle                 *string                `json:"job_job_title"`
	JobPostingLanguage          string                 `json:"job_posting_language"`
	JobOnetSoc                  string                 `json:"job_onet_soc"`
	JobOnetJobZone              string                 `json:"job_onet_job_zone"`
}
