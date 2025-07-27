package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"hire.ai/pkg/models"
)

type APIClient struct {
	httpClient *http.Client
	userAgent  string
	apiKeys    map[string]string
}

type APIJobBoard struct {
	Name        string            `json:"name"`
	BaseURL     string            `json:"baseUrl"`
	APIKey      string            `json:"apiKey,omitempty"`
	Endpoint    string            `json:"endpoint"`
	Method      string            `json:"method"`
	Headers     map[string]string `json:"headers,omitempty"`
	QueryParams map[string]string `json:"queryParams,omitempty"`
	RateLimit   int               `json:"rateLimit"`
	MaxResults  int               `json:"maxResults"`
}

type GitHubJob struct {
	ID          string    `json:"id"`
	Type        string    `json:"type"`
	URL         string    `json:"url"`
	CreatedAt   time.Time `json:"created_at"`
	Company     string    `json:"company"`
	Location    string    `json:"location"`
	Title       string    `json:"title"`
	Description string    `json:"description"`
	HowToApply  string    `json:"how_to_apply"`
	CompanyURL  string    `json:"company_url"`
	CompanyLogo string    `json:"company_logo"`
}

type RemoteOKJob struct {
	ID          int      `json:"id"`
	Slug        string   `json:"slug"`
	Company     string   `json:"company"`
	Position    string   `json:"position"`
	Description string   `json:"description"`
	Location    string   `json:"location"`
	Tags        []string `json:"tags"`
	Logo        string   `json:"logo"`
	URL         string   `json:"url"`
	Date        string   `json:"date"`
}

type USAJobsResponse struct {
	SearchResult struct {
		SearchResultItems []USAJob `json:"SearchResultItems"`
		UserArea          struct {
			NumberOfPages string `json:"NumberOfPages"`
			CurrentPage   string `json:"CurrentPage"`
		} `json:"UserArea"`
	} `json:"SearchResult"`
}

type USAJob struct {
	MatchedObjectDescriptor struct {
		PositionTitle    string `json:"PositionTitle"`
		OrganizationName string `json:"OrganizationName"`
		PositionLocation []struct {
			LocationName string `json:"LocationName"`
		} `json:"PositionLocation"`
		PositionRemuneration []struct {
			MinimumRange string `json:"MinimumRange"`
			MaximumRange string `json:"MaximumRange"`
		} `json:"PositionRemuneration"`
		QualificationSummary string `json:"QualificationSummary"`
		PositionURI          string `json:"PositionURI"`
		ApplyURI             []struct {
			ApplyOnlineURL string `json:"ApplyOnlineURL"`
		} `json:"ApplyURI"`
	} `json:"MatchedObjectDescriptor"`
}

func NewAPIClient(userAgent string, apiKeys map[string]string) *APIClient {
	return &APIClient{
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		userAgent: userAgent,
		apiKeys:   apiKeys,
	}
}

func (c *APIClient) FetchJobs(board APIJobBoard, keywords []string, location string) ([]models.Job, error) {
	switch strings.ToLower(board.Name) {
	case "github-jobs-api":
		return c.fetchGitHubJobs(board, keywords, location)
	case "remoteok-api":
		return c.fetchRemoteOKJobs(board)
	case "usajobs-api":
		return c.fetchUSAJobs(board, keywords, location)
	case "hn-jobs-api":
		return c.fetchHNWhoIsHiring(board)
	default:
		return c.fetchGenericAPI(board, keywords, location)
	}
}

func (c *APIClient) fetchGitHubJobs(board APIJobBoard, keywords []string, location string) ([]models.Job, error) {
	// GitHub Jobs API (deprecated but keeping for reference)
	params := url.Values{}
	if len(keywords) > 0 {
		params.Add("description", strings.Join(keywords, " "))
	}
	if location != "" {
		params.Add("location", location)
	}
	params.Add("full_time", "true")

	url := fmt.Sprintf("%s%s?%s", board.BaseURL, board.Endpoint, params.Encode())

	var githubJobs []GitHubJob
	if err := c.makeRequest(url, board.Headers, &githubJobs); err != nil {
		return nil, err
	}

	var jobs []models.Job
	for _, gj := range githubJobs {
		if len(jobs) >= board.MaxResults {
			break
		}

		job := models.NewJob(
			gj.Title,
			gj.Company,
			gj.Location,
			"", // GitHub Jobs doesn't provide salary
			gj.Description,
			gj.URL,
			board.Name,
		)
		jobs = append(jobs, *job)
	}

	return jobs, nil
}

func (c *APIClient) fetchRemoteOKJobs(board APIJobBoard) ([]models.Job, error) {
	url := fmt.Sprintf("%s%s", board.BaseURL, board.Endpoint)

	var remoteOKJobs []RemoteOKJob
	if err := c.makeRequest(url, board.Headers, &remoteOKJobs); err != nil {
		return nil, err
	}

	var jobs []models.Job
	for _, rj := range remoteOKJobs {
		if len(jobs) >= board.MaxResults {
			break
		}

		job := models.NewJob(
			rj.Position,
			rj.Company,
			rj.Location,
			"", // RemoteOK API doesn't always provide salary
			rj.Description,
			fmt.Sprintf("https://remoteok.io/remote-jobs/%s", rj.Slug),
			board.Name,
		)
		job.Keywords = rj.Tags
		jobs = append(jobs, *job)
	}

	return jobs, nil
}

func (c *APIClient) fetchUSAJobs(board APIJobBoard, keywords []string, location string) ([]models.Job, error) {
	params := url.Values{}
	if len(keywords) > 0 {
		params.Add("Keyword", strings.Join(keywords, " "))
	}
	if location != "" {
		params.Add("LocationName", location)
	}
	params.Add("ResultsPerPage", fmt.Sprintf("%d", board.MaxResults))
	params.Add("WhoMayApply", "All")

	url := fmt.Sprintf("%s%s?%s", board.BaseURL, board.Endpoint, params.Encode())

	headers := make(map[string]string)
	if board.Headers != nil {
		for k, v := range board.Headers {
			headers[k] = v
		}
	}
	if apiKey, exists := c.apiKeys["usajobs"]; exists {
		headers["Authorization-Key"] = apiKey
	}

	var response USAJobsResponse
	if err := c.makeRequest(url, headers, &response); err != nil {
		return nil, err
	}

	var jobs []models.Job
	for _, uj := range response.SearchResult.SearchResultItems {
		if len(jobs) >= board.MaxResults {
			break
		}

		md := uj.MatchedObjectDescriptor
		location := ""
		if len(md.PositionLocation) > 0 {
			location = md.PositionLocation[0].LocationName
		}

		salary := ""
		if len(md.PositionRemuneration) > 0 {
			rem := md.PositionRemuneration[0]
			salary = fmt.Sprintf("$%s - $%s", rem.MinimumRange, rem.MaximumRange)
		}

		applyURL := md.PositionURI
		if len(md.ApplyURI) > 0 {
			applyURL = md.ApplyURI[0].ApplyOnlineURL
		}

		job := models.NewJob(
			md.PositionTitle,
			md.OrganizationName,
			location,
			salary,
			md.QualificationSummary,
			applyURL,
			board.Name,
		)
		jobs = append(jobs, *job)
	}

	return jobs, nil
}

func (c *APIClient) fetchHNWhoIsHiring(board APIJobBoard) ([]models.Job, error) {
	// Fetch HackerNews "Who is Hiring" posts via HN API
	url := fmt.Sprintf("%s%s", board.BaseURL, board.Endpoint)

	var hnItems []map[string]interface{}
	if err := c.makeRequest(url, board.Headers, &hnItems); err != nil {
		return nil, err
	}

	var jobs []models.Job
	for _, item := range hnItems {
		if len(jobs) >= board.MaxResults {
			break
		}

		title, _ := item["title"].(string)
		text, _ := item["text"].(string)
		url, _ := item["url"].(string)

		if title != "" && text != "" {
			job := models.NewJob(
				title,
				"Various Companies (HN)",
				"Remote/Various",
				"",
				text,
				url,
				board.Name,
			)
			jobs = append(jobs, *job)
		}
	}

	return jobs, nil
}

func (c *APIClient) fetchGenericAPI(board APIJobBoard, keywords []string, location string) ([]models.Job, error) {
	params := url.Values{}
	for key, value := range board.QueryParams {
		switch {
		case strings.Contains(value, "{keywords}"):
			params.Add(key, strings.ReplaceAll(value, "{keywords}", strings.Join(keywords, " ")))
		case strings.Contains(value, "{location}"):
			params.Add(key, strings.ReplaceAll(value, "{location}", location))
		default:
			params.Add(key, value)
		}
	}

	url := fmt.Sprintf("%s%s?%s", board.BaseURL, board.Endpoint, params.Encode())

	var response map[string]interface{}
	if err := c.makeRequest(url, board.Headers, &response); err != nil {
		return nil, err
	}

	// Generic JSON parsing - this would need customization per API
	var jobs []models.Job
	if jobsData, exists := response["jobs"]; exists {
		if jobsList, ok := jobsData.([]interface{}); ok {
			for _, jobData := range jobsList {
				if len(jobs) >= board.MaxResults {
					break
				}

				if jobMap, ok := jobData.(map[string]interface{}); ok {
					title, _ := jobMap["title"].(string)
					company, _ := jobMap["company"].(string)
					location, _ := jobMap["location"].(string)
					description, _ := jobMap["description"].(string)
					url, _ := jobMap["url"].(string)

					if title != "" && company != "" {
						job := models.NewJob(title, company, location, "", description, url, board.Name)
						jobs = append(jobs, *job)
					}
				}
			}
		}
	}

	return jobs, nil
}

func (c *APIClient) makeRequest(url string, headers map[string]string, result interface{}) error {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return err
	}

	req.Header.Set("User-Agent", c.userAgent)
	req.Header.Set("Accept", "application/json")

	for key, value := range headers {
		req.Header.Set(key, value)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("API request failed with status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	return json.Unmarshal(body, result)
}
