package models

import (
	"crypto/md5"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

type Job struct {
	ID          string    `json:"id"`
	Title       string    `json:"title"`
	Company     string    `json:"company"`
	Location    string    `json:"location"`
	Salary      string    `json:"salary"`
	Description string    `json:"description"`
	Link        string    `json:"link"`
	Source      string    `json:"source"`
	Keywords    []string  `json:"keywords"`
	ScrapedAt   time.Time `json:"scraped_at"`
	UpdatedAt   time.Time `json:"updated_at"`
	IsActive    bool      `json:"is_active"`
	Relevance   float64   `json:"relevance"`
}

type JobFilter struct {
	Keywords  []string  `json:"keywords"`
	Location  string    `json:"location"`
	Sources   []string  `json:"sources"`
	MinSalary int       `json:"min_salary"`
	MaxSalary int       `json:"max_salary"`
	DateFrom  time.Time `json:"date_from"`
	DateTo    time.Time `json:"date_to"`
	IsActive  *bool     `json:"is_active"`
	Limit     int       `json:"limit"`
	Offset    int       `json:"offset"`
}

type JobSearchResult struct {
	Jobs       []Job `json:"jobs"`
	Total      int   `json:"total"`
	Page       int   `json:"page"`
	PerPage    int   `json:"per_page"`
	TotalPages int   `json:"total_pages"`
}

type JobStats struct {
	TotalJobs      int            `json:"total_jobs"`
	JobsBySource   map[string]int `json:"jobs_by_source"`
	JobsByLocation map[string]int `json:"jobs_by_location"`
	RecentJobs     int            `json:"recent_jobs"`
	LastScraped    time.Time      `json:"last_scraped"`
	Keywords       map[string]int `json:"keywords"`
}

func NewJob(title, company, location, salary, description, link, source string) *Job {
	job := &Job{
		Title:       strings.TrimSpace(title),
		Company:     strings.TrimSpace(company),
		Location:    strings.TrimSpace(location),
		Salary:      strings.TrimSpace(salary),
		Description: strings.TrimSpace(description),
		Link:        strings.TrimSpace(link),
		Source:      strings.TrimSpace(source),
		ScrapedAt:   time.Now(),
		UpdatedAt:   time.Now(),
		IsActive:    true,
		Relevance:   0.0,
	}

	job.ID = job.GenerateID()
	return job
}

func (j *Job) GenerateID() string {
	// Create unique ID based on title, company, and link
	data := fmt.Sprintf("%s|%s|%s",
		strings.ToLower(j.Title),
		strings.ToLower(j.Company),
		j.Link)

	hash := md5.Sum([]byte(data))
	return fmt.Sprintf("%x", hash)
}

func (j *Job) IsValid() bool {
	return j.Title != "" && j.Company != "" && j.Link != ""
}

func (j *Job) IsDuplicate(other *Job) bool {
	return j.ID == other.ID ||
		(strings.EqualFold(j.Title, other.Title) &&
			strings.EqualFold(j.Company, other.Company))
}

func (j *Job) ExtractKeywords() []string {
	text := strings.ToLower(j.Title + " " + j.Description)

	// Common tech keywords
	techKeywords := []string{
		"javascript", "python", "java", "golang", "go", "rust", "c++", "c#",
		"react", "vue", "angular", "node.js", "express", "django", "flask",
		"kubernetes", "docker", "aws", "azure", "gcp", "terraform",
		"mongodb", "postgresql", "mysql", "redis", "elasticsearch",
		"microservices", "api", "rest", "graphql", "grpc",
		"machine learning", "ai", "data science", "blockchain",
		"frontend", "backend", "fullstack", "devops", "mobile",
		"ios", "android", "react native", "flutter",
	}

	var foundKeywords []string
	for _, keyword := range techKeywords {
		if strings.Contains(text, keyword) {
			foundKeywords = append(foundKeywords, keyword)
		}
	}

	j.Keywords = foundKeywords
	return foundKeywords
}

func (j *Job) CalculateRelevance(searchKeywords []string) float64 {
	if len(searchKeywords) == 0 {
		return 0.0
	}

	text := strings.ToLower(j.Title + " " + j.Description)
	matches := 0

	for _, keyword := range searchKeywords {
		if strings.Contains(text, strings.ToLower(keyword)) {
			matches++
			// Give higher weight to title matches
			if strings.Contains(strings.ToLower(j.Title), strings.ToLower(keyword)) {
				matches++ // Double weight for title matches
			}
		}
	}

	j.Relevance = float64(matches) / float64(len(searchKeywords))
	return j.Relevance
}

func (j *Job) ToJSON() ([]byte, error) {
	return json.Marshal(j)
}

func (j *Job) FromJSON(data []byte) error {
	return json.Unmarshal(data, j)
}

func (j *Job) GetSalaryRange() (min, max int) {
	// Simple salary parsing - can be enhanced
	if j.Salary == "" {
		return 0, 0
	}

	// This is a basic implementation
	// In production, you'd want more sophisticated salary parsing
	salary := strings.ToLower(j.Salary)

	if strings.Contains(salary, "100k") || strings.Contains(salary, "100,000") {
		return 100000, 120000
	}
	if strings.Contains(salary, "80k") || strings.Contains(salary, "80,000") {
		return 80000, 100000
	}
	if strings.Contains(salary, "60k") || strings.Contains(salary, "60,000") {
		return 60000, 80000
	}

	return 0, 0
}

func (j *Job) IsRemote() bool {
	location := strings.ToLower(j.Location)
	return strings.Contains(location, "remote") ||
		strings.Contains(location, "anywhere") ||
		strings.Contains(location, "work from home")
}

func (j *Job) GetExperienceLevel() string {
	title := strings.ToLower(j.Title)
	description := strings.ToLower(j.Description)

	text := title + " " + description

	if strings.Contains(text, "senior") || strings.Contains(text, "sr.") ||
		strings.Contains(text, "lead") || strings.Contains(text, "principal") {
		return "senior"
	}

	if strings.Contains(text, "junior") || strings.Contains(text, "jr.") ||
		strings.Contains(text, "entry") || strings.Contains(text, "graduate") {
		return "junior"
	}

	return "mid"
}
