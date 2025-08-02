package api

import (
	"context"

	"hire.ai/pkg/providers"
)

// ProviderAdapter adapts providers.JobAPIProvider to api.JobAPIProvider
type ProviderAdapter struct {
	provider providers.JobAPIProvider
}

// NewProviderAdapter creates a new adapter
func NewProviderAdapter(provider providers.JobAPIProvider) JobAPIProvider {
	return &ProviderAdapter{provider: provider}
}

// GetName returns the provider name
func (a *ProviderAdapter) GetName() string {
	return a.provider.GetName()
}

// Search searches for jobs using the API
func (a *ProviderAdapter) Search(ctx context.Context, query SearchQuery) (*SearchResult, error) {
	// Convert API query to providers query
	providerQuery := providers.SearchQuery{
		Keywords:   query.Keywords,
		Location:   query.Location,
		Remote:     query.Remote,
		JobType:    query.JobType,
		Company:    query.Company,
		DatePosted: query.DatePosted,
		Limit:      query.Limit,
		Offset:     query.Offset,
	}

	if query.Salary != nil {
		providerQuery.Salary = &providers.Salary{
			Min:      query.Salary.Min,
			Max:      query.Salary.Max,
			Currency: query.Salary.Currency,
			Period:   query.Salary.Period,
		}
	}

	// Call provider
	result, err := a.provider.Search(ctx, providerQuery)
	if err != nil {
		return nil, err
	}

	// Convert providers result to API result
	return &SearchResult{
		Jobs:       result.Jobs,
		Total:      result.Total,
		Page:       result.Page,
		PerPage:    result.PerPage,
		HasMore:    result.HasMore,
		Provider:   result.Provider,
		SearchedAt: result.SearchedAt,
	}, nil
}

// IsConfigured checks if the provider is properly configured
func (a *ProviderAdapter) IsConfigured() bool {
	return a.provider.IsConfigured()
}

// GetRateLimit returns the rate limit information
func (a *ProviderAdapter) GetRateLimit() RateLimit {
	providerLimit := a.provider.GetRateLimit()
	return RateLimit{
		RequestsPerMinute: providerLimit.RequestsPerMinute,
		RequestsPerHour:   providerLimit.RequestsPerHour,
		RequestsPerDay:    providerLimit.RequestsPerDay,
		CooldownPeriod:    providerLimit.CooldownPeriod,
	}
}

// ValidateCredentials validates the API credentials
func (a *ProviderAdapter) ValidateCredentials(ctx context.Context) error {
	return a.provider.ValidateCredentials(ctx)
}
