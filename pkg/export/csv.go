package export

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"hire.ai/pkg/models"
)

type CSVExporter struct {
	outputDir string
}

// NewCSVExporter creates a new CSV exporter with the specified output directory
func NewCSVExporter(outputDir string) *CSVExporter {
	return &CSVExporter{
		outputDir: outputDir,
	}
}

func (e *CSVExporter) ExportJobs(jobs []models.Job, filename string) (string, error) {
	// Create output directory if it doesn't exist
	if err := os.MkdirAll(e.outputDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create output directory: %w", err)
	}

	// Generate filename if not provided
	if filename == "" {
		timestamp := time.Now().Format("2006-01-02_15-04-05")
		filename = fmt.Sprintf("jobs_export_%s.csv", timestamp)
	}

	// Ensure .csv extension
	if !strings.HasSuffix(filename, ".csv") {
		filename += ".csv"
	}

	filePath := filepath.Join(e.outputDir, filename)

	// Create CSV file
	file, err := os.Create(filePath)
	if err != nil {
		return "", fmt.Errorf("failed to create CSV file: %w", err)
	}
	defer file.Close()

	writer := csv.NewWriter(file)
	defer writer.Flush()

	// Write header
	headers := []string{
		"ID",
		"Title",
		"Company",
		"Location",
		"Salary",
		"Description",
		"Link",
		"Source",
		"Keywords",
		"Experience Level",
		"Is Remote",
		"Relevance Score",
		"Scraped At",
		"Updated At",
		"Is Active",
	}

	if err := writer.Write(headers); err != nil {
		return "", fmt.Errorf("failed to write CSV headers: %w", err)
	}

	// Write job data
	for _, job := range jobs {
		record := []string{
			job.ID,
			job.Title,
			job.Company,
			job.Location,
			job.Salary,
			cleanDescription(job.Description),
			job.Link,
			job.Source,
			strings.Join(job.Keywords, "; "),
			job.GetExperienceLevel(),
			strconv.FormatBool(job.IsRemote()),
			fmt.Sprintf("%.2f", job.Relevance),
			job.ScrapedAt.Format("2006-01-02 15:04:05"),
			job.UpdatedAt.Format("2006-01-02 15:04:05"),
			strconv.FormatBool(job.IsActive),
		}

		if err := writer.Write(record); err != nil {
			return "", fmt.Errorf("failed to write job record: %w", err)
		}
	}

	return filePath, nil
}

func (e *CSVExporter) ExportJobsWithStats(jobs []models.Job, stats *models.JobStats, filename string) (string, error) {
	// First export the jobs
	jobsFile, err := e.ExportJobs(jobs, filename)
	if err != nil {
		return "", err
	}

	// Create stats file
	statsFilename := strings.TrimSuffix(filename, ".csv") + "_stats.csv"
	if filename == "" {
		timestamp := time.Now().Format("2006-01-02_15-04-05")
		statsFilename = fmt.Sprintf("jobs_stats_%s.csv", timestamp)
	}

	statsPath := filepath.Join(e.outputDir, statsFilename)

	file, err := os.Create(statsPath)
	if err != nil {
		return jobsFile, fmt.Errorf("failed to create stats CSV file: %w", err)
	}
	defer file.Close()

	writer := csv.NewWriter(file)
	defer writer.Flush()

	// Write summary stats
	writer.Write([]string{"Metric", "Value"})
	writer.Write([]string{"Total Jobs", strconv.Itoa(stats.TotalJobs)})
	writer.Write([]string{"Recent Jobs (24h)", strconv.Itoa(stats.RecentJobs)})
	writer.Write([]string{"Last Scraped", stats.LastScraped.Format("2006-01-02 15:04:05")})

	// Empty row
	writer.Write([]string{})

	// Jobs by source
	writer.Write([]string{"Source", "Job Count"})
	for source, count := range stats.JobsBySource {
		writer.Write([]string{source, strconv.Itoa(count)})
	}

	// Empty row
	writer.Write([]string{})

	// Top locations
	writer.Write([]string{"Location", "Job Count"})
	locationCount := 0
	for location, count := range stats.JobsByLocation {
		if locationCount >= 10 { // Limit to top 10
			break
		}
		writer.Write([]string{location, strconv.Itoa(count)})
		locationCount++
	}

	// Empty row
	writer.Write([]string{})

	// Top keywords
	writer.Write([]string{"Keyword", "Frequency"})
	keywordCount := 0
	for keyword, count := range stats.Keywords {
		if keywordCount >= 20 { // Limit to top 20
			break
		}
		writer.Write([]string{keyword, strconv.Itoa(count)})
		keywordCount++
	}

	return jobsFile, nil
}

func cleanDescription(description string) string {
	// Remove newlines and excessive whitespace for CSV
	cleaned := strings.ReplaceAll(description, "\n", " ")
	cleaned = strings.ReplaceAll(cleaned, "\r", " ")
	cleaned = strings.ReplaceAll(cleaned, "\t", " ")

	// Replace multiple spaces with single space
	for strings.Contains(cleaned, "  ") {
		cleaned = strings.ReplaceAll(cleaned, "  ", " ")
	}

	// Trim and limit length
	cleaned = strings.TrimSpace(cleaned)
	if len(cleaned) > 500 {
		cleaned = cleaned[:500] + "..."
	}

	return cleaned
}
