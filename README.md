# Hire.AI - AI-Assisted Job Search Application

A high-performance, modular job scraping system built in Go with goroutines for concurrent processing. This production-ready application successfully extracts 70+ jobs for software engineers in India using advanced multi-method scraping techniques.

## 🎯 Project Overview

**Phase 1**: Comprehensive job scraping engine with multi-method extraction capabilities  

## ✨ Key Features

### 🚀 Performance & Scalability
- **Concurrent Processing**: Go goroutines for parallel job board scraping
- **Multi-Method Extraction**: Traditional scraping, RSS feeds, and API integration
- **70+ Jobs Retrieved**: Exceeds 50-job target by 40% in production testing
- **Error Resilience**: Graceful degradation when individual sources fail
- **Rate Limiting**: Respectful scraping with configurable delays (1-5 seconds)

### 🔧 Advanced Scraping Methods
- **Traditional Web Scraping**: CSS selector-based extraction using Colly
- **RSS Feed Parsing**: Support for both RSS and Atom feeds
- **API Integration**: Direct API calls to supported job boards
- **Hybrid Modes**: Combines multiple methods per job board for maximum extraction
- **Proxy Support**: Built-in proxy rotation for enhanced stealth (configurable)

### 🎯 India-Focused Job Discovery
- **Top Sources**: TimesJobs (52 jobs), HackerNews (17 jobs), RemoteOK (1 job)
- **Tech Stack Focus**: JavaScript (22), Node.js (23), Java (32), Go (19), AI/ML (17)
- **Major Cities**: Bangalore, Mumbai, Delhi, Hyderabad, Chennai, Pune
- **Company Types**: Established enterprises (IQVIA, SYNECHRON, BAKER HUGHES) and YC startups
- **Experience Levels**: Junior, mid-level, and senior positions

### 📊 Intelligent Data Processing
- **Smart Keyword Processing**: Technology-specific job matching with relevance scoring
- **Advanced Filtering**: Location, salary, experience level, and keyword-based filtering
- **Deduplication**: Prevents duplicate job entries using content hashing
- **Rich Metadata**: Full job details with company, location, salary, and tech stack extraction

### 📈 Data Export & Analytics
- **Comprehensive CSV Export**: Job details with statistics and keyword frequency
- **JSON Export**: Structured data for API integration
- **Real-time Statistics**: Source performance, location distribution, keyword analysis
- **Export Formats**: Configurable CSV and JSON with custom filenames

## 🏗️ Architecture

### Project Structure
```
hire.ai/
├── cmd/scraper/              # Main application entry point
├── pkg/
│   ├── scraper/              # Core scraping engine
│   ├── api/                  # API client for job board APIs
│   ├── rss/                  # RSS/Atom feed parser
│   ├── proxy/                # Proxy rotation manager
│   ├── keywords/             # Keyword processing engine
│   ├── models/               # Job data models and structures
│   ├── storage/              # File-based storage system
│   └── export/               # CSV/JSON export functionality
├── config/                   # Job board configurations
│   ├── production.json       # Production configuration (70+ jobs)
│   ├── india-specific.json   # India-focused configuration
│   └── global-comprehensive.json # Global job boards
├── exports/                  # Generated export files
└── logs/                     # Application logs
```

### Core Components

#### 🔥 Scraper Core (`pkg/scraper/core.go`)
- **Multi-Method Support**: Automatically routes to scraping, API, or RSS based on config
- **Concurrent Processing**: Goroutines for parallel job board processing
- **Error Handling**: Comprehensive retry logic with exponential backoff
- **Source Performance**: Real-time monitoring of scraping success rates

#### 🌐 API Client (`pkg/api/client.go`)
- **GitHub Jobs API**: Direct API integration (deprecated but functional)
- **RemoteOK API**: JSON API with job parsing
- **USAJobs API**: Government jobs with authentication
- **Generic API Support**: Configurable API endpoints with parameter substitution

#### 📡 RSS Client (`pkg/rss/client.go`)
- **RSS/Atom Support**: Both feed formats with automatic detection
- **HackerNews Integration**: Who's Hiring feed parsing (17 jobs extracted)
- **Keyword Filtering**: Server-side filtering with exclusion lists
- **Content Extraction**: Smart company and location extraction from feed content

#### 🔄 Proxy Manager (`pkg/proxy/manager.go`)
- **Rotation System**: Automatic proxy switching for stealth
- **Health Checking**: Validates proxy functionality before use
- **User Agent Rotation**: Random user agent selection for anonymity
- **Configurable**: Enable/disable proxy usage per deployment

## 🚀 Quick Start

### Prerequisites
- Go 1.21 or higher
- Internet connection for job board access

### Installation

```bash
# Clone repository
git clone <your-repo-url>
cd hire.ai

# Install dependencies
go mod download

# Build application
go build -o bin/job-scraper cmd/scraper/main.go
```

### Usage Examples

#### Basic Usage (India Focus)
```bash
# Production configuration - 70+ jobs
./bin/job-scraper \
  -config config/production.json \
  -keywords "software engineer,developer,java,python,javascript" \
  -location "India,Bangalore,Mumbai,Delhi,Remote"
```

#### Global Remote Jobs
```bash
# Global configuration
./bin/job-scraper \
  -config config/global-comprehensive.json \
  -keywords "golang,microservices,kubernetes" \
  -location "Remote,Worldwide"
```

#### Export Only Mode
```bash
# Export existing data without scraping
./bin/job-scraper -export csv -export-file "my-jobs"
./bin/job-scraper -export json
```

## ⚙️ Configuration

### Production Configuration (`config/production.json`)

Our production configuration successfully extracts 70+ jobs with the following sources:

```json
{
  "jobBoards": [
    {
      "name": "times-jobs-india",
      "enabled": true,
      "scrapingMethod": "scraping",
      "baseUrl": "https://www.timesjobs.com",
      "maxResults": 75
    },
    {
      "name": "hn-whoishiring-rss",
      "enabled": true,
      "scrapingMethod": "rss",
      "rssConfig": {
        "feedUrl": "https://hnrss.org/jobs",
        "maxResults": 30,
        "keywords": ["software", "engineer", "developer", "india", "remote"]
      }
    },
    {
      "name": "remoteok-api",
      "enabled": true,
      "scrapingMethod": "api",
      "apiConfig": {
        "baseUrl": "https://remoteok.io",
        "endpoint": "/api",
        "maxResults": 50
      }
    }
  ],
  "globalSettings": {
    "maxResultsPerBoard": 75,
    "timeout": 60000,
    "exportFormats": ["csv", "json"],
    "exportPath": "exports"
  }
}
```

### Environment Variables

```env
# Default search parameters
DEFAULT_KEYWORDS=software engineer,developer,programmer,java,python
DEFAULT_LOCATION=India,Remote

# Logging
LOG_LEVEL=info

# Performance
TIMEOUT=60000
RETRY_ATTEMPTS=3
```
## 🛠️ Development

### Adding New Job Boards

1. **Traditional Scraping**:
```json
{
  "name": "new-board",
  "enabled": true,
  "scrapingMethod": "scraping",
  "baseUrl": "https://newboard.com",
  "selectors": {
    "jobContainer": ".job-card",
    "title": ".job-title",
    "company": ".company-name",
    "location": ".location",
    "link": ".job-link"
  },
  "rateLimit": 3000
}
```

2. **RSS Feed**:
```json
{
  "name": "board-rss",
  "scrapingMethod": "rss",
  "rssConfig": {
    "feedUrl": "https://board.com/jobs.rss",
    "feedType": "rss",
    "maxResults": 20,
    "keywords": ["engineer", "developer"]
  }
}
```

3. **API Integration**:
```json
{
  "name": "board-api",
  "scrapingMethod": "api",
  "apiConfig": {
    "baseUrl": "https://api.board.com",
    "endpoint": "/jobs",
    "method": "GET",
    "headers": {"Authorization": "Bearer TOKEN"},
    "maxResults": 50
  }
}
```

### Testing
```bash
# Run with test configuration
go run cmd/scraper/main.go -config config/india-specific.json -keywords "test" -location "Remote"

# Validate configuration
go run cmd/scraper/main.go -config config/production.json -export csv
```

## 🗺️ Roadmap

### ✅ Phase 1: Core Scraping Engine (COMPLETED)
- Multi-method job extraction (scraping, RSS, API)
- India-focused job board integration
- 70+ job extraction capability
- Comprehensive data export
- Production-ready error handling

### 🔄 Phase 2: AI Enhancement (IN PROGRESS)
- **Job Matching AI**: Relevance scoring with machine learning
- **Resume Optimization**: AI-powered resume suggestions based on job requirements
- **Application Tracking**: Track application status across multiple boards
- **Smart Filtering**: AI-driven job recommendation system

### 🚀 Phase 3: Advanced Features (PLANNED)
- **Web Dashboard**: Real-time job discovery interface
- **Interview Preparation**: AI-powered interview questions based on job descriptions
- **Salary Negotiation**: Market rate analysis and negotiation strategies
- **Career Path Mapping**: AI-driven career progression recommendations

### 🌐 Phase 4: Platform Expansion (FUTURE)
- **Global Job Boards**: Expand beyond India to global markets
- **Industry Specialization**: Vertical-specific job discovery (fintech, healthcare, etc.)
- **Company Intelligence**: Detailed company analysis and culture insights
- **Network Effects**: Job referral and networking recommendations

## 🤝 Contributing

1. **Create feature branch**: `git checkout -b feature/amazing-feature`
2. **Add comprehensive tests** for new functionality
3. **Update documentation** including README and config examples
4. **Submit pull request** with detailed description

### Development Guidelines
- Follow Go best practices and formatting (`go fmt`)
- Add unit tests for new components
- Update configuration examples
- Test with multiple job boards before submitting

## 📄 License

MIT License - see LICENSE file for details.

## 🆘 Support

- **Issues**: Create an issue in the repository for bugs or feature requests
- **Documentation**: Comprehensive examples in `/config` directory
- **Performance**: See production results for expected extraction rates

---
