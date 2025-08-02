package scraper

import (
	"context"
	"encoding/json"
	"fmt"
	"math/rand"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/chromedp/chromedp"
	"github.com/gocolly/colly/v2"
	"github.com/gocolly/colly/v2/debug"
	"github.com/sirupsen/logrus"
	"golang.org/x/time/rate"

	"hire.ai/pkg/api"
	"hire.ai/pkg/models"
	"hire.ai/pkg/proxy"
	"hire.ai/pkg/rss"
)

type JobBoard struct {
	Name         string            `json:"name"`
	Enabled      bool              `json:"enabled"`
	BaseURL      string            `json:"baseUrl"`
	SearchPath   string            `json:"searchPath"`
	SearchParams map[string]string `json:"searchParams"`
	Selectors    Selectors         `json:"selectors"`
	RateLimit    int               `json:"rateLimit"`
	MaxResults   int               `json:"maxResults"`
	// New scraping methods
	ScrapingMethod string           `json:"scrapingMethod,omitempty"` // "scraping", "api", "rss"
	APIConfig      *api.APIJobBoard `json:"apiConfig,omitempty"`
	RSSConfig      *rss.RSSJobBoard `json:"rssConfig,omitempty"`
}

type Selectors struct {
	JobContainer string `json:"jobContainer"`
	Title        string `json:"title"`
	Company      string `json:"company"`
	Location     string `json:"location"`
	Salary       string `json:"salary"`
	Description  string `json:"description"`
	Link         string `json:"link"`
	// Fallback selectors
	TitleFallback    []string `json:"titleFallback,omitempty"`
	CompanyFallback  []string `json:"companyFallback,omitempty"`
	LocationFallback []string `json:"locationFallback,omitempty"`
}

type GlobalSettings struct {
	DefaultLocation    string             `json:"defaultLocation"`
	MaxResultsPerBoard int                `json:"maxResultsPerBoard"`
	UserAgent          string             `json:"userAgent"`
	Timeout            int                `json:"timeout"`
	RetryAttempts      int                `json:"retryAttempts"`
	TestMode           bool               `json:"testMode"`
	EnableLogging      bool               `json:"enableLogging"`
	ExportFormats      []string           `json:"exportFormats"`
	ExportPath         string             `json:"exportPath"`
	ProxyConfig        *proxy.ProxyConfig `json:"proxyConfig,omitempty"`
	APIKeys            map[string]string  `json:"apiKeys,omitempty"`
	Delay              struct {
		Min int `json:"min"`
		Max int `json:"max"`
	} `json:"delay"`
}

type Config struct {
	JobBoards      []JobBoard      `json:"jobBoards"`
	APIProviders   []api.APIConfig `json:"apiProviders"`
	GlobalSettings GlobalSettings  `json:"globalSettings"`
}

// Import the Job type from models package

type ScraperCore struct {
	config       Config
	rateLimiter  *rate.Limiter
	logger       *logrus.Logger
	client       *http.Client
	proxyManager *proxy.ProxyManager
	apiManager   *api.APIManager
	rssClient    *rss.RSSClient
}

type ScrapeResult struct {
	Jobs   []models.Job
	Error  error
	Source string
}

// NewScraperCore creates a new scraper core instance with the specified configuration
func NewScraperCore(configPath string) (*ScraperCore, error) {
	config, err := loadConfig(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to load config: %w", err)
	}

	logger := logrus.New()
	if config.GlobalSettings.EnableLogging {
		logger.SetLevel(logrus.InfoLevel)
	} else {
		logger.SetLevel(logrus.WarnLevel)
	}

	// Initialize proxy manager if configured
	var proxyManager *proxy.ProxyManager
	if config.GlobalSettings.ProxyConfig != nil && config.GlobalSettings.ProxyConfig.Enabled {
		proxyManager, err = proxy.NewProxyManager(*config.GlobalSettings.ProxyConfig)
		if err != nil {
			logger.Warnf("Failed to initialize proxy manager: %v", err)
		} else {
			logger.Infof("Initialized proxy manager with %d proxies", len(config.GlobalSettings.ProxyConfig.ProxyList))
			// Test proxies in background
			go proxyManager.TestAllProxies()
		}
	}

	// Use proxy manager for HTTP client if available
	var client *http.Client
	if proxyManager != nil {
		client = proxyManager.GetHTTPClient()
	} else {
		client = &http.Client{
			Timeout: time.Duration(config.GlobalSettings.Timeout) * time.Millisecond,
		}
	}

	rateLimiter := rate.NewLimiter(rate.Every(time.Millisecond*time.Duration(config.GlobalSettings.Delay.Min)), 1)

	// Initialize API manager
	apiManager := api.NewAPIManager(logger)

	// Load API keys from environment variables if not set in config
	for i := range config.APIProviders {
		if config.APIProviders[i].APIKey == "" {
			envKey := getAPIKeyEnvVar(config.APIProviders[i].Provider)
			if envValue := os.Getenv(envKey); envValue != "" {
				config.APIProviders[i].APIKey = envValue
				logger.Infof("Loaded API key for %s from environment variable %s", config.APIProviders[i].Provider, envKey)
			}
		}
	}

	// Register API providers
	if err := api.RegisterProviders(apiManager, config.APIProviders); err != nil {
		logger.Warnf("Failed to register API providers: %v", err)
	} else {
		enabledCount := 0
		for _, provider := range config.APIProviders {
			if provider.Enabled && provider.APIKey != "" {
				enabledCount++
			}
		}
		logger.Infof("Registered %d API providers (%d enabled and configured)", len(config.APIProviders), enabledCount)
	}

	// Initialize RSS client
	rssClient := rss.NewRSSClient(config.GlobalSettings.UserAgent)

	return &ScraperCore{
		config:       config,
		rateLimiter:  rateLimiter,
		logger:       logger,
		client:       client,
		proxyManager: proxyManager,
		apiManager:   apiManager,
		rssClient:    rssClient,
	}, nil
}

func (sc *ScraperCore) GetConfig() Config {
	return sc.config
}

// GetAPIStats returns statistics for all API providers
func (sc *ScraperCore) GetAPIStats() map[string]*api.APIStats {
	return sc.apiManager.GetStats()
}

// ValidateAPICredentials validates all configured API providers
func (sc *ScraperCore) ValidateAPICredentials() map[string]error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	return sc.apiManager.ValidateAllProviders(ctx)
}

// getAPIKeyEnvVar returns the environment variable name for the given provider
func getAPIKeyEnvVar(provider string) string {
	switch provider {
	case "usajobs":
		return "USAJOBS_API_KEY"
	case "reed":
		return "REED_API_KEY"
	case "jsearch":
		return "JSEARCH_API_KEY"
	default:
		return strings.ToUpper(provider) + "_API_KEY"
	}
}

func loadConfig(configPath string) (Config, error) {
	var config Config

	file, err := os.Open(configPath)
	if err != nil {
		return config, err
	}
	defer file.Close()

	decoder := json.NewDecoder(file)
	err = decoder.Decode(&config)
	return config, err
}

func (sc *ScraperCore) ScrapeAllBoards(keywords []string, location string) ([]models.Job, error) {
	var allJobs []models.Job
	var errors []string

	// First, try API providers
	sc.logger.Info("Attempting to fetch jobs using API providers...")
	apiJobs, apiErrors := sc.fetchFromAPIs(keywords, location)
	if len(apiJobs) > 0 {
		allJobs = append(allJobs, apiJobs...)
		sc.logger.Infof("Fetched %d jobs from API providers", len(apiJobs))
	}
	if len(apiErrors) > 0 {
		for _, err := range apiErrors {
			errors = append(errors, fmt.Sprintf("API: %v", err))
		}
	}

	// Then, fallback to scraping if needed or if APIs didn't provide enough results
	enabledBoards := sc.getEnabledBoards()
	if len(enabledBoards) > 0 {
		sc.logger.Info("Falling back to web scraping...")
		scraperJobs, scraperErrors := sc.scrapeBoards(enabledBoards, keywords, location)
		allJobs = append(allJobs, scraperJobs...)
		errors = append(errors, scraperErrors...)
	}

	if len(allJobs) == 0 && len(errors) > 0 {
		return nil, fmt.Errorf("all sources failed: %s", strings.Join(errors, "; "))
	}

	return allJobs, nil
}

// fetchFromAPIs attempts to fetch jobs from all configured API providers
func (sc *ScraperCore) fetchFromAPIs(keywords []string, location string) ([]models.Job, []error) {
	// Build search query
	query := api.SearchQuery{
		Keywords: keywords,
		Location: location,
		Limit:    100, // Default limit per provider
		Offset:   0,
	}

	// Search all configured providers
	results, err := sc.apiManager.SearchAll(context.Background(), query)
	if err != nil {
		return nil, []error{err}
	}

	// Aggregate jobs from all providers
	var allJobs []models.Job
	var errors []error

	for _, result := range results {
		if result != nil {
			allJobs = append(allJobs, result.Jobs...)
			sc.logger.Infof("API provider %s returned %d jobs", result.Provider, len(result.Jobs))
		}
	}

	return allJobs, errors
}

func (sc *ScraperCore) scrapeBoards(enabledBoards []JobBoard, keywords []string, location string) ([]models.Job, []string) {
	resultChan := make(chan ScrapeResult, len(enabledBoards))
	var wg sync.WaitGroup

	// Launch goroutine for each enabled job board
	for _, board := range enabledBoards {
		wg.Add(1)
		go func(board JobBoard) {
			defer wg.Done()

			// Rate limiting per board
			if err := sc.rateLimiter.Wait(context.Background()); err != nil {
				resultChan <- ScrapeResult{Error: err, Source: board.Name}
				return
			}

			jobs, err := sc.scrapeBoard(board, keywords, location)
			resultChan <- ScrapeResult{
				Jobs:   jobs,
				Error:  err,
				Source: board.Name,
			}
		}(board)
	}

	// Close channel when all goroutines complete
	go func() {
		wg.Wait()
		close(resultChan)
	}()

	// Collect results
	var allJobs []models.Job
	var errors []string

	for result := range resultChan {
		if result.Error != nil {
			errors = append(errors, fmt.Sprintf("%s: %v", result.Source, result.Error))
			sc.logger.Errorf("Failed to scrape %s: %v", result.Source, result.Error)
		} else {
			allJobs = append(allJobs, result.Jobs...)
			sc.logger.Infof("Successfully scraped %d jobs from %s", len(result.Jobs), result.Source)
		}
	}

	return allJobs, errors
}

func (sc *ScraperCore) scrapeBoard(board JobBoard, keywords []string, location string) ([]models.Job, error) {
	// Determine scraping method
	method := board.ScrapingMethod
	if method == "" {
		method = "scraping" // default
	}

	sc.logger.Infof("Scraping %s using method: %s", board.Name, method)

	switch method {
	case "api":
		// Legacy API config - now handled by the new API provider system
		return nil, fmt.Errorf("legacy API config no longer supported for %s, use apiProviders section instead", board.Name)

	case "rss":
		if board.RSSConfig != nil {
			return sc.rssClient.FetchJobs(*board.RSSConfig, keywords)
		}
		return nil, fmt.Errorf("RSS config not provided for %s", board.Name)

	default: // "scraping"
		keywordStr := strings.Join(keywords, " ")
		searchURL := sc.buildSearchURL(board, keywordStr, location)
		sc.logger.Infof("Scraping %s: %s", board.Name, searchURL)

		// Choose between JavaScript and HTTP scraping
		if sc.requiresJavaScript(board) {
			return sc.scrapeWithChromedp(board, searchURL)
		}

		return sc.scrapeWithColly(board, searchURL)
	}
}

func (sc *ScraperCore) scrapeWithColly(board JobBoard, url string) ([]models.Job, error) {
	var jobs []models.Job
	var mu sync.Mutex

	c := colly.NewCollector(
		colly.Debugger(&debug.LogDebugger{}),
	)

	// Set user agent (potentially random if proxy manager available)
	userAgent := sc.config.GlobalSettings.UserAgent
	if sc.proxyManager != nil {
		userAgent = sc.proxyManager.GetRandomUserAgent()
	}
	c.UserAgent = userAgent

	// Use proxy if available
	if sc.proxyManager != nil {
		proxyURL := sc.proxyManager.GetCurrentProxy()
		if proxyURL != "direct" {
			c.SetProxy(proxyURL)
			sc.logger.Debugf("Using proxy: %s", proxyURL)
		}
	}

	// Rate limiting
	c.Limit(&colly.LimitRule{
		DomainGlob:  "*",
		Parallelism: 1, // Reduced for better stealth
		Delay:       time.Duration(board.RateLimit) * time.Millisecond,
	})

	// Add random delays and headers for better stealth
	c.OnRequest(func(r *colly.Request) {
		// Add common headers
		r.Headers.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8")
		r.Headers.Set("Accept-Language", "en-US,en;q=0.5")
		r.Headers.Set("Accept-Encoding", "gzip, deflate")
		r.Headers.Set("Upgrade-Insecure-Requests", "1")
		r.Headers.Set("Sec-Fetch-Dest", "document")
		r.Headers.Set("Sec-Fetch-Mode", "navigate")
		r.Headers.Set("Sec-Fetch-Site", "none")

		// Random delay before request
		if sc.config.GlobalSettings.Delay.Max > sc.config.GlobalSettings.Delay.Min {
			randomDelay := rand.Intn(sc.config.GlobalSettings.Delay.Max-sc.config.GlobalSettings.Delay.Min) + sc.config.GlobalSettings.Delay.Min
			time.Sleep(time.Duration(randomDelay) * time.Millisecond)
		}
	})

	c.OnHTML(board.Selectors.JobContainer, func(e *colly.HTMLElement) {
		job := models.NewJob(
			strings.TrimSpace(e.ChildText(board.Selectors.Title)),
			strings.TrimSpace(e.ChildText(board.Selectors.Company)),
			strings.TrimSpace(e.ChildText(board.Selectors.Location)),
			strings.TrimSpace(e.ChildText(board.Selectors.Salary)),
			strings.TrimSpace(e.ChildText(board.Selectors.Description)),
			e.ChildAttr(board.Selectors.Link, "href"),
			board.Name,
		)

		// Resolve relative URLs
		if job.Link != "" && !strings.HasPrefix(job.Link, "http") {
			job.Link = e.Request.AbsoluteURL(job.Link)
		}

		if job.Title != "" && job.Company != "" {
			mu.Lock()
			jobs = append(jobs, *job)
			mu.Unlock()
		}
	})

	c.OnError(func(r *colly.Response, err error) {
		sc.logger.Errorf("Colly error on %s: %v", r.Request.URL, err)
	})

	err := c.Visit(url)
	if err != nil {
		return nil, fmt.Errorf("failed to visit %s: %w", url, err)
	}

	c.Wait()

	// Limit results - use board-specific limit or global default
	maxResults := board.MaxResults
	if maxResults == 0 {
		maxResults = sc.config.GlobalSettings.MaxResultsPerBoard
	}
	if len(jobs) > maxResults {
		jobs = jobs[:maxResults]
	}

	return jobs, nil
}

func (sc *ScraperCore) scrapeWithChromedp(board JobBoard, url string) ([]models.Job, error) {
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	ctx, cancel = context.WithTimeout(ctx, time.Duration(sc.config.GlobalSettings.Timeout)*time.Millisecond)
	defer cancel()

	type tempJob struct {
		Title       string `json:"title"`
		Company     string `json:"company"`
		Location    string `json:"location"`
		Salary      string `json:"salary"`
		Description string `json:"description"`
		Link        string `json:"link"`
	}

	var tempJobs []tempJob

	err := chromedp.Run(ctx,
		chromedp.Navigate(url),
		chromedp.WaitVisible(board.Selectors.JobContainer, chromedp.ByQuery),
		chromedp.Sleep(2*time.Second), // Allow dynamic content to load
		chromedp.Evaluate(`
			(() => {
				const jobs = [];
				const containers = document.querySelectorAll('`+board.Selectors.JobContainer+`');
				
				containers.forEach(container => {
					const job = {
						title: container.querySelector('`+board.Selectors.Title+`')?.textContent?.trim() || '',
						company: container.querySelector('`+board.Selectors.Company+`')?.textContent?.trim() || '',
						location: container.querySelector('`+board.Selectors.Location+`')?.textContent?.trim() || '',
						salary: container.querySelector('`+board.Selectors.Salary+`')?.textContent?.trim() || '',
						description: container.querySelector('`+board.Selectors.Description+`')?.textContent?.trim() || '',
						link: container.querySelector('`+board.Selectors.Link+`')?.href || ''
					};
					
					if (job.title && job.company) {
						jobs.push(job);
					}
				});
				
				return jobs;
			})()
		`, &tempJobs),
	)

	if err != nil {
		return nil, fmt.Errorf("chromedp error: %w", err)
	}

	// Process results
	processedJobs := make([]models.Job, 0, len(tempJobs))
	for _, tempJob := range tempJobs {
		job := models.NewJob(
			tempJob.Title,
			tempJob.Company,
			tempJob.Location,
			tempJob.Salary,
			tempJob.Description,
			tempJob.Link,
			board.Name,
		)
		processedJobs = append(processedJobs, *job)
	}

	// Limit results - use board-specific limit or global default
	maxResults := board.MaxResults
	if maxResults == 0 {
		maxResults = sc.config.GlobalSettings.MaxResultsPerBoard
	}
	if len(processedJobs) > maxResults {
		processedJobs = processedJobs[:maxResults]
	}

	return processedJobs, nil
}

func (sc *ScraperCore) buildSearchURL(board JobBoard, keywords, location string) string {
	baseURL := board.BaseURL + board.SearchPath

	params := make(map[string]string)
	for key, value := range board.SearchParams {
		switch {
		case strings.Contains(value, "{keywords}"):
			params[key] = strings.ReplaceAll(value, "{keywords}", keywords)
		case strings.Contains(value, "{location}"):
			params[key] = strings.ReplaceAll(value, "{location}", location)
		default:
			params[key] = value
		}
	}

	if len(params) == 0 {
		return baseURL
	}

	queryParams := make([]string, 0, len(params))
	for key, value := range params {
		queryParams = append(queryParams, fmt.Sprintf("%s=%s", key, value))
	}

	return fmt.Sprintf("%s?%s", baseURL, strings.Join(queryParams, "&"))
}

func (sc *ScraperCore) getEnabledBoards() []JobBoard {
	var enabled []JobBoard
	for _, board := range sc.config.JobBoards {
		if board.Enabled {
			enabled = append(enabled, board)
		}
	}
	return enabled
}

func (sc *ScraperCore) requiresJavaScript(board JobBoard) bool {
	// Force JavaScript rendering for more reliable scraping
	jsRequiredBoards := []string{
		"linkedin", "glassdoor", "indeed", "naukri", "angel", "wellfound",
		"ycombinator", "greenhouse", "lever", "workday", "bamboohr",
		"smartrecruiters", "jobvite", "icims", "bullhorn", "cornerstone",
	}

	boardName := strings.ToLower(board.Name)
	for _, jsBoard := range jsRequiredBoards {
		if strings.Contains(boardName, jsBoard) {
			return true
		}
	}

	// Also check URL patterns that typically require JS
	baseURL := strings.ToLower(board.BaseURL)
	jsPatterns := []string{"jobs.", "careers.", "apply.", "workday", "greenhouse", "lever"}
	for _, pattern := range jsPatterns {
		if strings.Contains(baseURL, pattern) {
			return true
		}
	}

	return false
}

func (sc *ScraperCore) randomDelay() {
	min := sc.config.GlobalSettings.Delay.Min
	max := sc.config.GlobalSettings.Delay.Max
	delay := rand.Intn(max-min) + min
	time.Sleep(time.Duration(delay) * time.Millisecond)
}
