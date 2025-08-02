package api

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
)

// APIManager manages multiple job API providers
type APIManager struct {
	providers map[string]JobAPIProvider
	stats     map[string]*APIStats
	logger    *logrus.Logger
	mutex     sync.RWMutex
}

// NewAPIManager creates a new API manager
func NewAPIManager(logger *logrus.Logger) *APIManager {
	return &APIManager{
		providers: make(map[string]JobAPIProvider),
		stats:     make(map[string]*APIStats),
		logger:    logger,
	}
}

// RegisterProvider registers a new job API provider
func (m *APIManager) RegisterProvider(provider JobAPIProvider) error {
	m.mutex.Lock()
	defer m.mutex.Unlock()

	name := provider.GetName()
	if _, exists := m.providers[name]; exists {
		return fmt.Errorf("provider %s already registered", name)
	}

	m.providers[name] = provider
	m.stats[name] = &APIStats{
		Provider: name,
	}

	m.logger.Infof("Registered API provider: %s", name)
	return nil
}

// GetProvider returns a specific provider by name
func (m *APIManager) GetProvider(name string) (JobAPIProvider, error) {
	m.mutex.RLock()
	defer m.mutex.RUnlock()

	provider, exists := m.providers[name]
	if !exists {
		return nil, fmt.Errorf("provider %s not found", name)
	}

	return provider, nil
}

// GetConfiguredProviders returns all configured and enabled providers
func (m *APIManager) GetConfiguredProviders() []JobAPIProvider {
	m.mutex.RLock()
	defer m.mutex.RUnlock()

	var configured []JobAPIProvider
	for _, provider := range m.providers {
		if provider.IsConfigured() {
			configured = append(configured, provider)
		}
	}

	return configured
}

// SearchAll searches all configured providers concurrently
func (m *APIManager) SearchAll(ctx context.Context, query SearchQuery) ([]*SearchResult, error) {
	providers := m.GetConfiguredProviders()
	if len(providers) == 0 {
		return nil, fmt.Errorf("no configured API providers available")
	}

	resultChan := make(chan *SearchResult, len(providers))
	errorChan := make(chan error, len(providers))

	// Launch searches concurrently
	var wg sync.WaitGroup
	for _, provider := range providers {
		wg.Add(1)
		go func(p JobAPIProvider) {
			defer wg.Done()

			start := time.Now()
			result, err := m.searchWithStats(ctx, p, query)
			duration := time.Since(start)

			// Update stats
			m.updateStats(p.GetName(), err == nil, duration, result)

			if err != nil {
				m.logger.Warnf("Provider %s search failed: %v", p.GetName(), err)
				errorChan <- fmt.Errorf("provider %s: %w", p.GetName(), err)
				return
			}

			resultChan <- result
		}(provider)
	}

	// Wait for all goroutines to complete
	go func() {
		wg.Wait()
		close(resultChan)
		close(errorChan)
	}()

	// Collect results
	var results []*SearchResult
	var errors []error

	for {
		select {
		case result, ok := <-resultChan:
			if !ok {
				resultChan = nil
			} else {
				results = append(results, result)
			}
		case err, ok := <-errorChan:
			if !ok {
				errorChan = nil
			} else {
				errors = append(errors, err)
			}
		}

		if resultChan == nil && errorChan == nil {
			break
		}
	}

	// Log summary
	m.logger.Infof("API search completed: %d successful, %d failed providers",
		len(results), len(errors))

	if len(results) == 0 && len(errors) > 0 {
		return nil, fmt.Errorf("all providers failed: %v", errors)
	}

	return results, nil
}

// SearchProvider searches a specific provider
func (m *APIManager) SearchProvider(ctx context.Context, providerName string, query SearchQuery) (*SearchResult, error) {
	provider, err := m.GetProvider(providerName)
	if err != nil {
		return nil, err
	}

	if !provider.IsConfigured() {
		return nil, fmt.Errorf("provider %s is not configured", providerName)
	}

	start := time.Now()
	result, err := m.searchWithStats(ctx, provider, query)
	duration := time.Since(start)

	// Update stats
	m.updateStats(providerName, err == nil, duration, result)

	return result, err
}

// searchWithStats performs a search with rate limiting and error handling
func (m *APIManager) searchWithStats(ctx context.Context, provider JobAPIProvider, query SearchQuery) (*SearchResult, error) {
	// Apply rate limiting
	rateLimit := provider.GetRateLimit()
	if rateLimit.CooldownPeriod > 0 {
		time.Sleep(rateLimit.CooldownPeriod)
	}

	// Perform search
	result, err := provider.Search(ctx, query)
	if err != nil {
		return nil, err
	}

	// Set provider name and search time
	result.Provider = provider.GetName()
	result.SearchedAt = time.Now()

	return result, nil
}

// updateStats updates provider statistics
func (m *APIManager) updateStats(providerName string, success bool, duration time.Duration, result *SearchResult) {
	m.mutex.Lock()
	defer m.mutex.Unlock()

	stats, exists := m.stats[providerName]
	if !exists {
		stats = &APIStats{Provider: providerName}
		m.stats[providerName] = stats
	}

	stats.TotalRequests++
	stats.LastUsed = time.Now()

	if success {
		stats.SuccessRequests++
		if result != nil {
			stats.TotalJobs += len(result.Jobs)
		}
	} else {
		stats.FailedRequests++
	}

	// Update average latency
	if stats.TotalRequests == 1 {
		stats.AverageLatency = duration
	} else {
		// Running average
		stats.AverageLatency = time.Duration(
			(int64(stats.AverageLatency)*int64(stats.TotalRequests-1) + int64(duration)) / int64(stats.TotalRequests),
		)
	}
}

// GetStats returns statistics for all providers
func (m *APIManager) GetStats() map[string]*APIStats {
	m.mutex.RLock()
	defer m.mutex.RUnlock()

	// Create a copy to avoid concurrent access issues
	statsCopy := make(map[string]*APIStats)
	for name, stats := range m.stats {
		statsCopy[name] = &APIStats{
			Provider:        stats.Provider,
			TotalRequests:   stats.TotalRequests,
			SuccessRequests: stats.SuccessRequests,
			FailedRequests:  stats.FailedRequests,
			TotalJobs:       stats.TotalJobs,
			AverageLatency:  stats.AverageLatency,
			LastUsed:        stats.LastUsed,
		}
	}

	return statsCopy
}

// ValidateAllProviders validates credentials for all providers
func (m *APIManager) ValidateAllProviders(ctx context.Context) map[string]error {
	m.mutex.RLock()
	providers := make([]JobAPIProvider, 0, len(m.providers))
	for _, provider := range m.providers {
		providers = append(providers, provider)
	}
	m.mutex.RUnlock()

	results := make(map[string]error)
	var wg sync.WaitGroup

	for _, provider := range providers {
		wg.Add(1)
		go func(p JobAPIProvider) {
			defer wg.Done()
			name := p.GetName()

			if !p.IsConfigured() {
				results[name] = fmt.Errorf("provider not configured")
				return
			}

			err := p.ValidateCredentials(ctx)
			results[name] = err
		}(provider)
	}

	wg.Wait()
	return results
}
