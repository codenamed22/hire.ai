.PHONY: build run clean deps test install dev

# Binary name
BINARY_NAME=job-scraper

# Build the application
build:
	go build -o bin/$(BINARY_NAME) cmd/scraper/main.go

# Install dependencies
deps:
	go mod tidy
	go mod download

# Run the application with India production config (70+ jobs)
run: build
	./bin/$(BINARY_NAME) -config config/production.json -keywords "software engineer,developer,java,python,javascript" -location "India,Bangalore,Mumbai,Delhi,Remote" -verbose

# Run with custom keywords
run-custom:
	@if [ -z "$(KEYWORDS)" ]; then \
		echo "Usage: make run-custom KEYWORDS=\"your keywords\" [LOCATION=\"location\"]"; \
		exit 1; \
	fi
	./bin/$(BINARY_NAME) -keywords "$(KEYWORDS)" -location "$(or $(LOCATION),Remote)" -verbose

# Development run with hot reload (requires 'go install github.com/cosmtrek/air@latest')
dev:
	air -c .air.toml

# Clean build artifacts
clean:
	rm -rf bin/
	rm -rf data/
	rm -rf logs/

# Test the application
test:
	go test ./...

# Install the binary to GOPATH/bin
install: build
	cp bin/$(BINARY_NAME) $(GOPATH)/bin/

# Run India-specific configuration
run-india:
	./bin/$(BINARY_NAME) -config config/india-specific.json -keywords "$(or $(KEYWORDS),software engineer,java,python)" -location "$(or $(LOCATION),India,Bangalore,Mumbai)" -verbose

# Run global configuration
run-global:
	./bin/$(BINARY_NAME) -config config/global-comprehensive.json -keywords "$(or $(KEYWORDS),software engineer,remote)" -location "$(or $(LOCATION),Remote,Worldwide)" -verbose

# Export existing data
export-csv:
	./bin/$(BINARY_NAME) -export csv

export-json:
	./bin/$(BINARY_NAME) -export json

# Agent system commands
setup-agents:
	python setup_agents.py

agents-help:
	python agents/cli.py --help

# Run orchestrator with default search
run-agents:
	python agents/cli.py orchestrator "software engineer,developer,python,java" --location "India,Remote,Bangalore" --max-results 30

# Interactive question mode
ask-agents:
	python agents/cli.py question

# Run specific agent search
run-agent-search:
	@if [ -z "$(KEYWORDS)" ]; then \
		echo "Usage: make run-agent-search KEYWORDS=\"your keywords\" [LOCATION=\"location\"]"; \
		exit 1; \
	fi
	python agents/cli.py agent "$(KEYWORDS)" --location "$(or $(LOCATION),India,Remote)" --max-results 25

# Database search commands
run-database-search:
	@if [ -z "$(KEYWORDS)" ]; then \
		echo "Usage: make run-database-search KEYWORDS=\"your keywords\" [LOCATION=\"location\"]"; \
		exit 1; \
	fi
	python3 agents/cli.py database "$(KEYWORDS)" --location "$(or $(LOCATION),India,Remote)" --max-results 25

# Hybrid search commands  
run-hybrid-search:
	@if [ -z "$(KEYWORDS)" ]; then \
		echo "Usage: make run-hybrid-search KEYWORDS=\"your keywords\" [LOCATION=\"location\"]"; \
		exit 1; \
	fi
	python3 agents/cli.py hybrid "$(KEYWORDS)" --location "$(or $(LOCATION),India,Remote)" --max-results 50

# Database operations
db-setup:
	python3 bin/migrate.py -action=up -verbose

db-status:
	python3 bin/migrate.py -action=status

db-reset:
	python3 bin/migrate.py -action=down && python3 bin/migrate.py -action=up -verbose

# Setup development environment
setup:
	@echo "Setting up development environment..."
	go mod init hire.ai || true
	go mod tidy
	mkdir -p data logs config
	cp .env.example .env
	@echo "Setup complete! Edit .env file with your settings."

# Show help
help:
	@echo "Available commands:"
	@echo ""
	@echo "Go Scraper Commands:"
	@echo "  build        - Build the Go application"
	@echo "  run          - Run production config for India (70+ jobs)"
	@echo "  run-custom   - Run with custom keywords (KEYWORDS and LOCATION vars)"
	@echo "  run-india    - Run India-specific job boards"
	@echo "  run-global   - Run global/remote job boards"
	@echo "  export-csv   - Export existing data to CSV"
	@echo "  export-json  - Export existing data to JSON"
	@echo ""
	@echo "Agentic AI Commands:"
	@echo "  setup-agents         - Setup Python agent environment"
	@echo "  run-agents           - Run AI orchestrator with default search"
	@echo "  ask-agents           - Interactive AI question mode"
	@echo "  run-agent-search     - Run specific agent search (requires KEYWORDS)"
	@echo "  run-database-search  - Search jobs in database (requires KEYWORDS)"
	@echo "  run-hybrid-search    - Hybrid database + scraping search (requires KEYWORDS)"
	@echo "  agents-help          - Show detailed agent CLI help"
	@echo ""
	@echo "Database Commands:"
	@echo "  db-setup             - Setup database schema and tables"
	@echo "  db-status            - Show database status and statistics"
	@echo "  db-reset             - Reset database (WARNING: destroys data)"
	@echo ""
	@echo "Development Commands:"
	@echo "  dev          - Run in development mode with hot reload"
	@echo "  deps         - Install Go dependencies"
	@echo "  test         - Run tests"
	@echo "  clean        - Clean build artifacts"
	@echo "  install      - Install binary to GOPATH/bin"
	@echo "  setup        - Setup development environment"
	@echo ""
	@echo "Examples:"
	@echo "  # Traditional Go scraping"
	@echo "  make run                                          # Production India config (70+ jobs)"
	@echo "  make run-custom KEYWORDS=\"python,django,api\" LOCATION=\"Mumbai\""
	@echo ""
	@echo "  # AI-powered agentic search"
	@echo "  make setup-agents                                 # First-time setup"
	@echo "  make run-agents                                   # AI orchestrator search"
	@echo "  make ask-agents                                   # Ask AI questions"
	@echo "  make run-agent-search KEYWORDS=\"react,frontend\"  # Specific AI search"
	@echo "  make run-database-search KEYWORDS=\"python,django\" # Search database only"
	@echo "  make run-hybrid-search KEYWORDS=\"java,spring\"    # Database + scraping"