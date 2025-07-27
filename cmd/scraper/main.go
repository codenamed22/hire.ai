package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/joho/godotenv"
	"github.com/sirupsen/logrus"

	"hire.ai/pkg/export"
	"hire.ai/pkg/keywords"
	"hire.ai/pkg/models"
	"hire.ai/pkg/scraper"
	"hire.ai/pkg/storage"
)

func main() {
	// Load environment variables
	godotenv.Load()

	// Command line flags
	var (
		keywordsFlag   = flag.String("keywords", "", "Job search keywords (comma-separated)")
		locationFlag   = flag.String("location", "", "Job location")
		configFlag     = flag.String("config", "config/job-boards.json", "Path to job boards configuration")
		dataFlag       = flag.String("data", "data", "Data directory for storage")
		verboseFlag    = flag.Bool("verbose", false, "Verbose logging")
		exportFlag     = flag.String("export", "", "Export format (csv, json) - if specified, exports and exits")
		exportFileFlag = flag.String("export-file", "", "Custom export filename")
	)
	flag.Parse()

	// Setup logging
	logger := logrus.New()
	if *verboseFlag {
		logger.SetLevel(logrus.DebugLevel)
	}

	// Initialize components
	app, err := NewApplication(*configFlag, *dataFlag, logger)
	if err != nil {
		logger.Fatalf("Failed to initialize application: %v", err)
	}
	defer app.Close()

	// Check if we should export existing data without scraping
	if *exportFlag != "" {
		if err := app.ExportExistingData(*exportFlag, *exportFileFlag); err != nil {
			logger.Fatalf("Export failed: %v", err)
		}
		return
	}

	// Get keywords from flag or environment
	keywordsInput := *keywordsFlag
	if keywordsInput == "" {
		keywordsInput = os.Getenv("DEFAULT_KEYWORDS")
	}
	if keywordsInput == "" {
		logger.Fatal("No keywords provided. Use -keywords flag or set DEFAULT_KEYWORDS environment variable")
	}

	// Get location from flag or environment
	location := *locationFlag
	if location == "" {
		location = os.Getenv("DEFAULT_LOCATION")
	}
	if location == "" {
		location = "Remote"
	}

	logger.Infof("Starting job scraper with keywords: %s, location: %s", keywordsInput, location)

	// Process keywords
	keywordsList := strings.Split(keywordsInput, ",")
	for i := range keywordsList {
		keywordsList[i] = strings.TrimSpace(keywordsList[i])
	}

	// Run the scraping process
	if err := app.ScrapeJobs(keywordsList, location); err != nil {
		logger.Fatalf("Scraping failed: %v", err)
	}

	// Display results
	if err := app.DisplayResults(); err != nil {
		logger.Errorf("Failed to display results: %v", err)
	}

	// Auto-export if configured
	if len(app.config.GlobalSettings.ExportFormats) > 0 {
		for _, format := range app.config.GlobalSettings.ExportFormats {
			if err := app.ExportExistingData(format, ""); err != nil {
				logger.Warnf("Auto-export to %s failed: %v", format, err)
			} else {
				logger.Infof("Auto-exported data to %s format", format)
			}
		}
	}
}

type Application struct {
	scraper          *scraper.ScraperCore
	storage          storage.Storage
	keywordProcessor *keywords.KeywordProcessor
	csvExporter      *export.CSVExporter
	logger           *logrus.Logger
	config           *scraper.Config
}

func NewApplication(configPath, dataDir string, logger *logrus.Logger) (*Application, error) {
	// Initialize scraper
	scraperCore, err := scraper.NewScraperCore(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to create scraper: %w", err)
	}

	// Get config
	config := scraperCore.GetConfig()

	// Initialize storage
	fileStorage, err := storage.NewFileStorage(dataDir)
	if err != nil {
		return nil, fmt.Errorf("failed to create storage: %w", err)
	}

	// Initialize keyword processor
	keywordProcessor := keywords.NewKeywordProcessor()

	// Initialize CSV exporter
	exportPath := config.GlobalSettings.ExportPath
	if exportPath == "" {
		exportPath = "exports"
	}
	csvExporter := export.NewCSVExporter(exportPath)

	return &Application{
		scraper:          scraperCore,
		storage:          fileStorage,
		keywordProcessor: keywordProcessor,
		csvExporter:      csvExporter,
		logger:           logger,
		config:           &config,
	}, nil
}

func (app *Application) ScrapeJobs(keywordsList []string, location string) error {
	start := time.Now()
	app.logger.Infof("Starting job scraping process...")

	// Process keywords
	keywordsStr := strings.Join(keywordsList, " ")
	query := app.keywordProcessor.ProcessKeywords(keywordsStr)
	query.Location = location

	app.logger.Infof("Processed keywords: %v", query.Keywords)

	// Scrape jobs using goroutines
	jobs, err := app.scraper.ScrapeAllBoards(query.Keywords, location)
	if err != nil {
		return fmt.Errorf("scraping failed: %w", err)
	}

	app.logger.Infof("Scraped %d jobs in %v", len(jobs), time.Since(start))

	// Calculate relevance scores
	for i := range jobs {
		jobs[i].CalculateRelevance(query.Keywords)
	}

	// Store jobs
	if err := app.storage.Store(jobs); err != nil {
		return fmt.Errorf("failed to store jobs: %w", err)
	}

	app.logger.Infof("Successfully stored %d jobs", len(jobs))
	return nil
}

func (app *Application) DisplayResults() error {
	// Get recent jobs
	filter := models.JobFilter{
		DateFrom: time.Now().Add(-24 * time.Hour),
		Limit:    20,
		Offset:   0,
	}

	result, err := app.storage.Search(filter)
	if err != nil {
		return fmt.Errorf("failed to search jobs: %w", err)
	}

	// Display summary
	stats, err := app.storage.GetStats()
	if err != nil {
		app.logger.Warnf("Failed to get stats: %v", err)
	} else {
		app.displayStats(stats)
	}

	// Display recent jobs
	app.displayJobs(result.Jobs)

	return nil
}

func (app *Application) displayStats(stats *models.JobStats) {
	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Println("JOB SCRAPING SUMMARY")
	fmt.Println(strings.Repeat("=", 60))
	fmt.Printf("Total Jobs Found: %d\n", stats.TotalJobs)
	fmt.Printf("Recent Jobs (24h): %d\n", stats.RecentJobs)
	fmt.Printf("Last Scraped: %s\n", stats.LastScraped.Format("2006-01-02 15:04:05"))

	fmt.Println("\nJobs by Source:")
	for source, count := range stats.JobsBySource {
		fmt.Printf("  %-15s: %d\n", source, count)
	}

	fmt.Println("\nTop Locations:")
	count := 0
	for location, jobCount := range stats.JobsByLocation {
		if count >= 5 {
			break
		}
		fmt.Printf("  %-20s: %d\n", location, jobCount)
		count++
	}

	fmt.Println("\nTop Keywords:")
	count = 0
	for keyword, keywordCount := range stats.Keywords {
		if count >= 10 {
			break
		}
		fmt.Printf("  %-15s: %d\n", keyword, keywordCount)
		count++
	}
}

func (app *Application) displayJobs(jobs []models.Job) {
	if len(jobs) == 0 {
		fmt.Println("\nNo recent jobs found.")
		return
	}

	fmt.Println("\n" + strings.Repeat("=", 80))
	fmt.Printf("RECENT JOBS (%d found)\n", len(jobs))
	fmt.Println(strings.Repeat("=", 80))

	for i, job := range jobs {
		if i >= 10 { // Limit to first 10 for readability
			break
		}

		fmt.Printf("\n%d. %s\n", i+1, job.Title)
		fmt.Printf("   Company: %s\n", job.Company)
		fmt.Printf("   Location: %s\n", job.Location)
		if job.Salary != "" {
			fmt.Printf("   Salary: %s\n", job.Salary)
		}
		fmt.Printf("   Source: %s\n", job.Source)
		fmt.Printf("   Relevance: %.2f\n", job.Relevance)
		fmt.Printf("   Link: %s\n", job.Link)
		fmt.Printf("   Scraped: %s\n", job.ScrapedAt.Format("2006-01-02 15:04"))

		if len(job.Keywords) > 0 {
			fmt.Printf("   Keywords: %s\n", strings.Join(job.Keywords, ", "))
		}

		if job.Description != "" && len(job.Description) > 100 {
			fmt.Printf("   Description: %s...\n", job.Description[:100])
		} else if job.Description != "" {
			fmt.Printf("   Description: %s\n", job.Description)
		}
	}

	if len(jobs) > 10 {
		fmt.Printf("\n... and %d more jobs. Use the web interface or storage API to view all results.\n", len(jobs)-10)
	}
}

func (app *Application) ExportExistingData(format, filename string) error {
	// Get all jobs from storage
	jobs, err := app.storage.GetAll()
	if err != nil {
		return fmt.Errorf("failed to get jobs for export: %w", err)
	}

	if len(jobs) == 0 {
		app.logger.Warn("No jobs found to export")
		return fmt.Errorf("no jobs found to export")
	}

	switch strings.ToLower(format) {
	case "csv":
		// Get stats for comprehensive export
		stats, err := app.storage.GetStats()
		if err != nil {
			app.logger.Warnf("Failed to get stats for export: %v", err)
			// Export without stats
			filePath, err := app.csvExporter.ExportJobs(jobs, filename)
			if err != nil {
				return fmt.Errorf("CSV export failed: %w", err)
			}
			app.logger.Infof("Exported %d jobs to CSV: %s", len(jobs), filePath)
		} else {
			// Export with stats
			filePath, err := app.csvExporter.ExportJobsWithStats(jobs, stats, filename)
			if err != nil {
				return fmt.Errorf("CSV export with stats failed: %w", err)
			}
			app.logger.Infof("Exported %d jobs with stats to CSV: %s", len(jobs), filePath)
		}
	case "json":
		return app.exportToJSON(jobs, filename)
	default:
		return fmt.Errorf("unsupported export format: %s", format)
	}

	return nil
}

func (app *Application) exportToJSON(jobs []models.Job, filename string) error {
	// Create output directory
	exportPath := app.config.GlobalSettings.ExportPath
	if exportPath == "" {
		exportPath = "exports"
	}

	if err := os.MkdirAll(exportPath, 0755); err != nil {
		return fmt.Errorf("failed to create export directory: %w", err)
	}

	// Generate filename if not provided
	if filename == "" {
		timestamp := time.Now().Format("2006-01-02_15-04-05")
		filename = fmt.Sprintf("jobs_export_%s.json", timestamp)
	}

	// Ensure .json extension
	if !strings.HasSuffix(filename, ".json") {
		filename += ".json"
	}

	filePath := fmt.Sprintf("%s/%s", exportPath, filename)

	// Export to JSON
	file, err := os.Create(filePath)
	if err != nil {
		return fmt.Errorf("failed to create JSON file: %w", err)
	}
	defer file.Close()

	// Write pretty JSON
	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")

	if err := encoder.Encode(jobs); err != nil {
		return fmt.Errorf("failed to encode jobs to JSON: %w", err)
	}

	app.logger.Infof("Exported %d jobs to JSON: %s", len(jobs), filePath)
	return nil
}

func (app *Application) Close() {
	if app.storage != nil {
		app.storage.Close()
	}
}
