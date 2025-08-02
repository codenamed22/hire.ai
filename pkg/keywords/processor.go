package keywords

import (
	"regexp"
	"strings"
)

type KeywordProcessor struct {
	synonyms         map[string][]string
	exclusions       []string
	jobTitlePatterns []*regexp.Regexp
}

type SearchQuery struct {
	Keywords   []string `json:"keywords"`
	Location   string   `json:"location"`
	Synonyms   []string `json:"synonyms"`
	Exclusions []string `json:"exclusions"`
}

// NewKeywordProcessor creates a new keyword processor instance
func NewKeywordProcessor() *KeywordProcessor {
	return &KeywordProcessor{
		synonyms:   getDefaultSynonyms(),
		exclusions: getDefaultExclusions(),
		jobTitlePatterns: []*regexp.Regexp{
			regexp.MustCompile(`(?i)\b(senior|sr|junior|jr|lead|principal|staff|entry.level)\b`),
			regexp.MustCompile(`(?i)\b(engineer|developer|programmer|architect|analyst|manager)\b`),
			regexp.MustCompile(`(?i)\b(full.stack|frontend|backend|frontend|devops|mobile)\b`),
		},
	}
}

func (kp *KeywordProcessor) ProcessKeywords(input string) SearchQuery {
	// Clean and split input
	keywords := kp.cleanAndSplit(input)

	// Expand with synonyms
	expandedKeywords := kp.expandWithSynonyms(keywords)

	// Remove exclusions
	filteredKeywords := kp.filterExclusions(expandedKeywords)

	// Extract job level and type patterns
	patterns := kp.extractJobPatterns(strings.Join(keywords, " "))

	return SearchQuery{
		Keywords:   filteredKeywords,
		Synonyms:   patterns,
		Exclusions: kp.exclusions,
	}
}

func (kp *KeywordProcessor) cleanAndSplit(input string) []string {
	// Remove special characters and normalize
	input = strings.ToLower(input)
	input = regexp.MustCompile(`[^\w\s\-\+\.]`).ReplaceAllString(input, " ")

	// Split by common delimiters
	keywords := regexp.MustCompile(`[\s,;|]+`).Split(input, -1)

	// Filter empty strings and short terms
	var cleaned []string
	for _, keyword := range keywords {
		keyword = strings.TrimSpace(keyword)
		if len(keyword) >= 2 {
			cleaned = append(cleaned, keyword)
		}
	}

	return cleaned
}

func (kp *KeywordProcessor) expandWithSynonyms(keywords []string) []string {
	expandedSet := make(map[string]bool)

	// Add original keywords
	for _, keyword := range keywords {
		expandedSet[keyword] = true
	}

	// Add synonyms
	for _, keyword := range keywords {
		if synonyms, exists := kp.synonyms[keyword]; exists {
			for _, synonym := range synonyms {
				expandedSet[synonym] = true
			}
		}
	}

	// Convert back to slice
	var expanded []string
	for keyword := range expandedSet {
		expanded = append(expanded, keyword)
	}

	return expanded
}

func (kp *KeywordProcessor) filterExclusions(keywords []string) []string {
	var filtered []string

	for _, keyword := range keywords {
		excluded := false
		for _, exclusion := range kp.exclusions {
			if strings.Contains(strings.ToLower(keyword), strings.ToLower(exclusion)) {
				excluded = true
				break
			}
		}
		if !excluded {
			filtered = append(filtered, keyword)
		}
	}

	return filtered
}

func (kp *KeywordProcessor) extractJobPatterns(text string) []string {
	var patterns []string

	for _, pattern := range kp.jobTitlePatterns {
		matches := pattern.FindAllString(text, -1)
		patterns = append(patterns, matches...)
	}

	return patterns
}

func (kp *KeywordProcessor) GenerateSearchVariations(query SearchQuery) []SearchQuery {
	variations := []SearchQuery{query}

	// Create variations with different keyword combinations
	if len(query.Keywords) > 1 {
		// Individual keywords
		for _, keyword := range query.Keywords {
			variations = append(variations, SearchQuery{
				Keywords: []string{keyword},
				Location: query.Location,
			})
		}

		// Pairs of keywords
		for i := 0; i < len(query.Keywords)-1; i++ {
			for j := i + 1; j < len(query.Keywords); j++ {
				variations = append(variations, SearchQuery{
					Keywords: []string{query.Keywords[i], query.Keywords[j]},
					Location: query.Location,
				})
			}
		}
	}

	return variations
}

func (kp *KeywordProcessor) AddCustomSynonyms(keyword string, synonyms []string) {
	if kp.synonyms == nil {
		kp.synonyms = make(map[string][]string)
	}
	kp.synonyms[keyword] = synonyms
}

func (kp *KeywordProcessor) AddExclusions(exclusions []string) {
	kp.exclusions = append(kp.exclusions, exclusions...)
}

func getDefaultSynonyms() map[string][]string {
	return map[string][]string{
		"software engineer": {"developer", "programmer", "software developer", "software engineer", "swe"},
		"developer":         {"engineer", "programmer", "dev", "software developer"},
		"frontend":          {"front-end", "front end", "ui developer", "web developer"},
		"backend":           {"back-end", "back end", "server-side", "api developer"},
		"fullstack":         {"full-stack", "full stack", "full-stack developer"},
		"devops":            {"dev ops", "site reliability engineer", "sre", "infrastructure engineer"},
		"mobile":            {"ios", "android", "react native", "flutter", "mobile developer"},
		"javascript":        {"js", "node.js", "nodejs", "react", "vue", "angular"},
		"python":            {"django", "flask", "fastapi", "python developer"},
		"java":              {"spring", "spring boot", "kotlin", "java developer"},
		"golang":            {"go", "go developer", "golang developer"},
		"rust":              {"rust developer", "systems programming"},
		"remote":            {"work from home", "telecommute", "distributed", "wfh"},
		"senior":            {"sr", "lead", "principal", "staff"},
		"junior":            {"jr", "entry level", "associate", "graduate"},
	}
}

func getDefaultExclusions() []string {
	return []string{
		"internship",
		"unpaid",
		"volunteer",
		"commission only",
		"mlm",
		"pyramid",
		"door to door",
		"cold calling",
		"insurance sales",
	}
}
