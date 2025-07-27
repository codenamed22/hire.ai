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
	@echo "  build        - Build the application"
	@echo "  run          - Run production config for India (70+ jobs)"
	@echo "  run-custom   - Run with custom keywords (KEYWORDS and LOCATION vars)"
	@echo "  run-india    - Run India-specific job boards"
	@echo "  run-global   - Run global/remote job boards"
	@echo "  export-csv   - Export existing data to CSV"
	@echo "  export-json  - Export existing data to JSON"
	@echo "  dev          - Run in development mode with hot reload"
	@echo "  deps         - Install dependencies"
	@echo "  test         - Run tests"
	@echo "  clean        - Clean build artifacts"
	@echo "  install      - Install binary to GOPATH/bin"
	@echo "  setup        - Setup development environment"
	@echo ""
	@echo "Examples:"
	@echo "  make run                                          # Production India config (70+ jobs)"
	@echo "  make run-custom KEYWORDS=\"python,django,api\" LOCATION=\"Mumbai\""
	@echo "  make run-india KEYWORDS=\"java,spring,microservices\""
	@echo "  make run-global KEYWORDS=\"golang,kubernetes,remote\""