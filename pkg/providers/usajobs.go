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

// USAJobsProvider implements the JobAPIProvider interface for USAJobs API
type USAJobsProvider struct {
	config APIConfig
	client *http.Client
}

// NewUSAJobsProvider creates a new USAJobs API provider
func NewUSAJobsProvider(config APIConfig, timeout time.Duration) *USAJobsProvider {
	return &USAJobsProvider{
		config: config,
		client: &http.Client{
			Timeout: timeout,
		},
	}
}

// GetName returns the provider name
func (p *USAJobsProvider) GetName() string {
	return "usajobs"
}

// Search searches for jobs using the USAJobs API
func (p *USAJobsProvider) Search(ctx context.Context, query SearchQuery) (*SearchResult, error) {
	if !p.IsConfigured() {
		return nil, fmt.Errorf("USAJobs provider not configured")
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

	// Add required headers
	req.Header.Set("Host", "data.usajobs.gov")
	req.Header.Set("User-Agent", p.config.Headers["User-Agent"])
	req.Header.Set("Authorization-Key", p.config.APIKey)

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
	var apiResp USAJobsResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	// Convert to our standard format
	jobs := p.convertJobs(apiResp.SearchResult.SearchResultItems)

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
func (p *USAJobsProvider) IsConfigured() bool {
	return p.config.Enabled && p.config.APIKey != ""
}

// GetRateLimit returns the rate limit information
func (p *USAJobsProvider) GetRateLimit() RateLimit {
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
func (p *USAJobsProvider) ValidateCredentials(ctx context.Context) error {
	// Test with a simple search
	testQuery := SearchQuery{
		Keywords: []string{"software"},
		Location: "Washington, DC",
		Limit:    1,
		Offset:   0,
	}

	_, err := p.Search(ctx, testQuery)
	return err
}

// buildSearchURL builds the search URL with parameters
func (p *USAJobsProvider) buildSearchURL(query SearchQuery) (string, error) {
	baseURL := p.config.BaseURL
	if baseURL == "" {
		baseURL = "https://data.usajobs.gov/api/Search"
	}

	u, err := url.Parse(baseURL)
	if err != nil {
		return "", err
	}

	params := url.Values{}

	// Add keywords
	if len(query.Keywords) > 0 {
		params.Set("Keyword", strings.Join(query.Keywords, " "))
	}

	// Add location
	if query.Location != "" {
		params.Set("LocationName", query.Location)
	}

	// Add remote work option
	if query.Remote {
		params.Set("RemoteIndicator", "true")
	}

	// Add job type
	if query.JobType != "" {
		switch strings.ToLower(query.JobType) {
		case "full-time":
			params.Set("PositionScheduleTypeCode", "1")
		case "part-time":
			params.Set("PositionScheduleTypeCode", "2")
		}
	}

	// Add pagination
	params.Set("ResultsPerPage", strconv.Itoa(query.Limit))
	if query.Offset > 0 {
		params.Set("Page", strconv.Itoa(query.Offset/query.Limit+1))
	}

	// Add date posted filter
	if query.DatePosted != "" {
		days := parseDatePosted(query.DatePosted)
		if days > 0 {
			params.Set("DatePosted", strconv.Itoa(days))
		}
	}

	u.RawQuery = params.Encode()
	return u.String(), nil
}

// convertJobs converts USAJobs API response to our standard Job format
func (p *USAJobsProvider) convertJobs(items []USAJobsItem) []models.Job {
	var jobs []models.Job

	for _, item := range items {
		job := models.Job{
			ID:          fmt.Sprintf("usajobs_%s", item.MatchedObjectDescriptor.PositionID),
			Title:       item.MatchedObjectDescriptor.PositionTitle,
			Company:     item.MatchedObjectDescriptor.OrganizationName,
			Location:    p.formatLocation(item.MatchedObjectDescriptor.PositionLocationDisplay),
			Description: item.MatchedObjectDescriptor.UserArea.Details.JobSummary,
			Source:      "USAJobs",
			Link:        item.MatchedObjectDescriptor.PositionURI,
			ScrapedAt:   time.Now(),
			Salary:      p.formatSalary(item.MatchedObjectDescriptor),
		}

		// Add keywords from the job title and description
		job.Keywords = extractKeywords(job.Title, job.Description)

		jobs = append(jobs, job)
	}

	return jobs
}

// formatLocation formats the location display
func (p *USAJobsProvider) formatLocation(locations []string) string {
	if len(locations) == 0 {
		return "Not specified"
	}
	return strings.Join(locations, ", ")
}

// formatSalary formats salary information
func (p *USAJobsProvider) formatSalary(descriptor USAJobsDescriptor) string {
	if len(descriptor.PositionRemuneration) == 0 {
		return ""
	}

	remuneration := descriptor.PositionRemuneration[0]
	if remuneration.MinimumRange != "" && remuneration.MaximumRange != "" {
		return fmt.Sprintf("$%s - $%s per year", remuneration.MinimumRange, remuneration.MaximumRange)
	}
	if remuneration.MinimumRange != "" {
		return fmt.Sprintf("$%s+ per year", remuneration.MinimumRange)
	}
	return ""
}

// parseDatePosted converts date posted string to days
func parseDatePosted(datePosted string) int {
	switch strings.ToLower(datePosted) {
	case "1d", "today":
		return 1
	case "3d":
		return 3
	case "7d", "week":
		return 7
	case "14d":
		return 14
	case "30d", "month":
		return 30
	default:
		return 0
	}
}

// extractKeywords extracts keywords from title and description
func extractKeywords(title, description string) []string {
	// Simple keyword extraction - can be enhanced with NLP
	commonTechKeywords := []string{
		"software", "engineer", "developer", "programming", "java", "python",
		"javascript", "react", "node", "aws", "docker", "kubernetes", "api",
		"database", "sql", "nosql", "mongodb", "postgresql", "mysql",
		"frontend", "backend", "fullstack", "devops", "cloud", "agile",
	}

	var keywords []string
	text := strings.ToLower(title + " " + description)

	for _, keyword := range commonTechKeywords {
		if strings.Contains(text, keyword) {
			keywords = append(keywords, keyword)
		}
	}

	return keywords
}

// USAJobs API response structures
type USAJobsResponse struct {
	LanguageCode string              `json:"LanguageCode"`
	SearchResult USAJobsSearchResult `json:"SearchResult"`
}

type USAJobsSearchResult struct {
	SearchResultCount    int           `json:"SearchResultCount"`
	SearchResultCountAll int           `json:"SearchResultCountAll"`
	SearchResultItems    []USAJobsItem `json:"SearchResultItems"`
}

type USAJobsItem struct {
	MatchedObjectDescriptor USAJobsDescriptor `json:"MatchedObjectDescriptor"`
	MatchedObjectId         string            `json:"MatchedObjectId"`
	RelevanceRank           int               `json:"RelevanceRank"`
}

type USAJobsDescriptor struct {
	PositionID              string                `json:"PositionID"`
	PositionTitle           string                `json:"PositionTitle"`
	PositionURI             string                `json:"PositionURI"`
	ApplyURI                []string              `json:"ApplyURI"`
	PositionLocationDisplay []string              `json:"PositionLocationDisplay"`
	OrganizationName        string                `json:"OrganizationName"`
	DepartmentName          string                `json:"DepartmentName"`
	PositionRemuneration    []USAJobsRemuneration `json:"PositionRemuneration"`
	PositionStartDate       string                `json:"PositionStartDate"`
	PositionEndDate         string                `json:"PositionEndDate"`
	PublicationStartDate    string                `json:"PublicationStartDate"`
	ApplicationCloseDate    string                `json:"ApplicationCloseDate"`
	PositionSchedule        []USAJobsSchedule     `json:"PositionSchedule"`
	UserArea                USAJobsUserArea       `json:"UserArea"`
}

type USAJobsRemuneration struct {
	MinimumRange     string `json:"MinimumRange"`
	MaximumRange     string `json:"MaximumRange"`
	RateIntervalCode string `json:"RateIntervalCode"`
	Description      string `json:"Description"`
}

type USAJobsSchedule struct {
	Name string `json:"Name"`
	Code string `json:"Code"`
}

type USAJobsUserArea struct {
	Details USAJobsDetails `json:"Details"`
}

type USAJobsDetails struct {
	JobSummary          string `json:"JobSummary"`
	WhoMayApply         string `json:"WhoMayApply"`
	LowGrade            string `json:"LowGrade"`
	HighGrade           string `json:"HighGrade"`
	PromotionPotential  string `json:"PromotionPotential"`
	OrganizationCodes   string `json:"OrganizationCodes"`
	Relocation          string `json:"Relocation"`
	HiringPath          string `json:"HiringPath"`
	TotalOpenings       string `json:"TotalOpenings"`
	Keyword             string `json:"Keyword"`
	MajorDuties         string `json:"MajorDuties"`
	Education           string `json:"Education"`
	Requirements        string `json:"Requirements"`
	Evaluations         string `json:"Evaluations"`
	HowToApply          string `json:"HowToApply"`
	WhatToExpectNext    string `json:"WhatToExpectNext"`
	RequiredDocuments   string `json:"RequiredDocuments"`
	Benefits            string `json:"Benefits"`
	BenefitsUrl         string `json:"BenefitsUrl"`
	BenefitsDisplayText string `json:"BenefitsDisplayText"`
	OtherInformation    string `json:"OtherInformation"`
}
