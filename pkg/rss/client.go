package rss

import (
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"hire.ai/pkg/models"
)

type RSSFeed struct {
	XMLName xml.Name `xml:"rss"`
	Channel Channel  `xml:"channel"`
}

type AtomFeed struct {
	XMLName xml.Name    `xml:"feed"`
	Title   string      `xml:"title"`
	Entries []AtomEntry `xml:"entry"`
}

type Channel struct {
	Title       string `xml:"title"`
	Description string `xml:"description"`
	Link        string `xml:"link"`
	Items       []Item `xml:"item"`
}

type Item struct {
	Title       string `xml:"title"`
	Description string `xml:"description"`
	Link        string `xml:"link"`
	PubDate     string `xml:"pubDate"`
	GUID        string `xml:"guid"`
	Category    string `xml:"category"`
}

type AtomEntry struct {
	Title   string `xml:"title"`
	Summary string `xml:"summary"`
	Link    struct {
		Href string `xml:"href,attr"`
	} `xml:"link"`
	Published string `xml:"published"`
	ID        string `xml:"id"`
}

type RSSJobBoard struct {
	Name         string   `json:"name"`
	FeedURL      string   `json:"feedUrl"`
	FeedType     string   `json:"feedType"` // "rss" or "atom"
	MaxResults   int      `json:"maxResults"`
	Keywords     []string `json:"keywords,omitempty"`
	ExcludeWords []string `json:"excludeWords,omitempty"`
}

type RSSClient struct {
	httpClient *http.Client
	userAgent  string
}

func NewRSSClient(userAgent string) *RSSClient {
	return &RSSClient{
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		userAgent: userAgent,
	}
}

func (c *RSSClient) FetchJobs(board RSSJobBoard, keywords []string) ([]models.Job, error) {
	resp, err := c.httpClient.Get(board.FeedURL)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch RSS feed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("RSS feed returned status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read RSS response: %w", err)
	}

	var jobs []models.Job
	if board.FeedType == "atom" {
		jobs, err = c.parseAtomFeed(body, board, keywords)
	} else {
		jobs, err = c.parseRSSFeed(body, board, keywords)
	}

	if err != nil {
		return nil, err
	}

	// Filter and limit results
	filteredJobs := c.filterJobs(jobs, board, keywords)
	if len(filteredJobs) > board.MaxResults && board.MaxResults > 0 {
		filteredJobs = filteredJobs[:board.MaxResults]
	}

	return filteredJobs, nil
}

func (c *RSSClient) parseRSSFeed(body []byte, board RSSJobBoard, keywords []string) ([]models.Job, error) {
	var feed RSSFeed
	if err := xml.Unmarshal(body, &feed); err != nil {
		return nil, fmt.Errorf("failed to parse RSS feed: %w", err)
	}

	var jobs []models.Job
	for _, item := range feed.Channel.Items {
		job := c.itemToJob(item, board.Name)
		if job != nil {
			jobs = append(jobs, *job)
		}
	}

	return jobs, nil
}

func (c *RSSClient) parseAtomFeed(body []byte, board RSSJobBoard, keywords []string) ([]models.Job, error) {
	var feed AtomFeed
	if err := xml.Unmarshal(body, &feed); err != nil {
		return nil, fmt.Errorf("failed to parse Atom feed: %w", err)
	}

	var jobs []models.Job
	for _, entry := range feed.Entries {
		job := c.entryToJob(entry, board.Name)
		if job != nil {
			jobs = append(jobs, *job)
		}
	}

	return jobs, nil
}

func (c *RSSClient) itemToJob(item Item, source string) *models.Job {
	if item.Title == "" {
		return nil
	}

	// Extract company from title or description
	company := c.extractCompany(item.Title, item.Description)
	location := c.extractLocation(item.Title, item.Description)

	job := models.NewJob(
		item.Title,
		company,
		location,
		"", // RSS feeds rarely have salary info
		item.Description,
		item.Link,
		source,
	)

	return job
}

func (c *RSSClient) entryToJob(entry AtomEntry, source string) *models.Job {
	if entry.Title == "" {
		return nil
	}

	company := c.extractCompany(entry.Title, entry.Summary)
	location := c.extractLocation(entry.Title, entry.Summary)

	job := models.NewJob(
		entry.Title,
		company,
		location,
		"",
		entry.Summary,
		entry.Link.Href,
		source,
	)

	return job
}

func (c *RSSClient) extractCompany(title, description string) string {
	// Simple company extraction logic
	text := title + " " + description
	text = strings.ToLower(text)

	// Look for common patterns
	patterns := []string{
		"at ", "@ ", "company:", "employer:", "hiring:",
	}

	for _, pattern := range patterns {
		if idx := strings.Index(text, pattern); idx != -1 {
			start := idx + len(pattern)
			remaining := text[start:]

			// Extract next word(s) as company name
			words := strings.Fields(remaining)
			if len(words) > 0 {
				// Take first 1-3 words as company name
				end := len(words)
				if end > 3 {
					end = 3
				}
				return strings.Join(words[:end], " ")
			}
		}
	}

	return "Unknown Company"
}

func (c *RSSClient) extractLocation(title, description string) string {
	text := title + " " + description
	text = strings.ToLower(text)

	// Common location indicators
	locations := []string{
		"remote", "anywhere", "worldwide", "global",
		"san francisco", "new york", "london", "berlin",
		"toronto", "sydney", "tokyo", "mumbai", "bangalore",
		"austin", "seattle", "boston", "chicago", "denver",
	}

	for _, loc := range locations {
		if strings.Contains(text, loc) {
			return strings.Title(loc)
		}
	}

	return "Not Specified"
}

func (c *RSSClient) filterJobs(jobs []models.Job, board RSSJobBoard, searchKeywords []string) []models.Job {
	var filtered []models.Job

	for _, job := range jobs {
		// Check if job matches keywords
		if !c.matchesKeywords(job, board.Keywords, searchKeywords) {
			continue
		}

		// Check if job contains excluded words
		if c.containsExcludedWords(job, board.ExcludeWords) {
			continue
		}

		// Calculate relevance
		allKeywords := append(board.Keywords, searchKeywords...)
		job.CalculateRelevance(allKeywords)

		filtered = append(filtered, job)
	}

	return filtered
}

func (c *RSSClient) matchesKeywords(job models.Job, boardKeywords, searchKeywords []string) bool {
	if len(boardKeywords) == 0 && len(searchKeywords) == 0 {
		return true // No filtering
	}

	text := strings.ToLower(job.Title + " " + job.Description)
	allKeywords := append(boardKeywords, searchKeywords...)

	for _, keyword := range allKeywords {
		if strings.Contains(text, strings.ToLower(keyword)) {
			return true
		}
	}

	return false
}

func (c *RSSClient) containsExcludedWords(job models.Job, excludeWords []string) bool {
	if len(excludeWords) == 0 {
		return false
	}

	text := strings.ToLower(job.Title + " " + job.Description)

	for _, word := range excludeWords {
		if strings.Contains(text, strings.ToLower(word)) {
			return true
		}
	}

	return false
}
