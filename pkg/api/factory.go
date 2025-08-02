package api

import (
	"fmt"
	"time"

	"hire.ai/pkg/providers"
)

// ProviderFactory creates API providers based on configuration
type ProviderFactory struct{}

// NewProviderFactory creates a new provider factory
func NewProviderFactory() *ProviderFactory {
	return &ProviderFactory{}
}

// CreateProvider creates a provider instance based on the configuration
func (f *ProviderFactory) CreateProvider(config APIConfig) (JobAPIProvider, error) {
	// Parse timeout
	timeout, err := time.ParseDuration(config.Timeout)
	if err != nil {
		timeout = 30 * time.Second // default timeout
	}

	// Convert API config to providers config
	providerConfig := providers.APIConfig{
		Name:        config.Name,
		Enabled:     config.Enabled,
		Provider:    config.Provider,
		BaseURL:     config.BaseURL,
		APIKey:      config.APIKey,
		SecretKey:   config.SecretKey,
		RateLimit:   providers.RateLimitConfig(config.RateLimit),
		MaxResults:  config.MaxResults,
		Timeout:     config.Timeout,
		RetryConfig: providers.RetryConfig(config.RetryConfig),
		Headers:     config.Headers,
		Params:      config.Params,
	}

	var provider providers.JobAPIProvider
	switch config.Provider {
	case "usajobs":
		provider = providers.NewUSAJobsProvider(providerConfig, timeout)
	case "reed":
		provider = providers.NewReedProvider(providerConfig, timeout)
	case "jsearch":
		provider = providers.NewJSearchProvider(providerConfig, timeout)
	default:
		return nil, fmt.Errorf("unknown provider type: %s", config.Provider)
	}

	// Wrap with adapter
	return NewProviderAdapter(provider), nil
}

// RegisterProviders registers all configured providers with the API manager
func RegisterProviders(manager *APIManager, configs []APIConfig) error {
	factory := NewProviderFactory()

	for _, config := range configs {
		if !config.Enabled {
			continue
		}

		provider, err := factory.CreateProvider(config)
		if err != nil {
			return fmt.Errorf("failed to create provider %s: %w", config.Name, err)
		}

		if err := manager.RegisterProvider(provider); err != nil {
			return fmt.Errorf("failed to register provider %s: %w", config.Name, err)
		}
	}

	return nil
}
