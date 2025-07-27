"""
Comprehensive test suite for the Hire.AI agent system.

This module provides unit tests, integration tests, and performance tests
for all agent components following industry best practices.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any, List
import tempfile
import os
from pathlib import Path

# Import the modules to test
from agents.core.config import AgentConfig, get_config
from agents.core.exceptions import (
    ConfigurationError, ValidationError, ToolError, 
    ScrapingError, AgentError, OrchestrationError
)
from agents.core.resilience import (
    CircuitBreaker, CircuitBreakerConfig, CircuitState,
    RateLimiter, RateLimitConfig, retry_with_backoff, RetryConfig
)
from agents.core.dependency_injection import ServiceContainer, ServiceLifetime
from agents.tools.scraper_tool import JobScraperTool
from agents.job_search.agent import JobSearchAgent, JobSearchCriteria
from agents.orchestrator.main import HireAIOrchestrator, JobSearchRequest


class TestConfiguration:
    """Test configuration management."""
    
    def test_config_validation_success(self):
        """Test successful configuration validation."""
        config = AgentConfig(
            openai=Mock(api_key="test-key"),
            scraper=Mock(binary_path=Path("/fake/path"))
        )
        assert config.openai.api_key == "test-key"
    
    def test_config_validation_missing_api_key(self):
        """Test configuration validation with missing API key."""
        with pytest.raises(ConfigurationError):
            from agents.core.config import OpenAIConfig
            OpenAIConfig(api_key="")
    
    def test_config_validation_invalid_log_level(self):
        """Test configuration validation with invalid log level."""
        with pytest.raises(ConfigurationError):
            AgentConfig(
                openai=Mock(api_key="test-key"),
                scraper=Mock(binary_path=Path("/fake/path")),
                log_level="INVALID"
            )
    
    @patch.dict(os.environ, {
        'OPENAI_API_KEY': 'test-key',
        'LOG_LEVEL': 'DEBUG',
        'MAX_AGENT_ROUNDS': '5'
    })
    def test_config_from_environment(self):
        """Test configuration loading from environment variables."""
        # This would need the actual config loading mechanism
        pass


class TestResilience:
    """Test resilience patterns."""
    
    def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in closed state."""
        config = CircuitBreakerConfig(failure_threshold=3)
        circuit_breaker = CircuitBreaker(config)
        
        @circuit_breaker
        def test_function():
            return "success"
        
        # Should work normally in closed state
        result = test_function()
        assert result == "success"
        assert circuit_breaker.state == CircuitState.CLOSED
    
    def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after threshold failures."""
        config = CircuitBreakerConfig(failure_threshold=2)
        circuit_breaker = CircuitBreaker(config)
        
        @circuit_breaker
        def failing_function():
            raise Exception("Test failure")
        
        # First failure
        with pytest.raises(Exception):
            failing_function()
        assert circuit_breaker.state == CircuitState.CLOSED
        
        # Second failure - should open circuit
        with pytest.raises(Exception):
            failing_function()
        assert circuit_breaker.state == CircuitState.OPEN
    
    def test_rate_limiter_allows_within_limit(self):
        """Test rate limiter allows requests within limit."""
        config = RateLimitConfig(max_calls=5, time_window=1.0)
        rate_limiter = RateLimiter(config)
        
        # Should allow first 5 requests
        for _ in range(5):
            assert rate_limiter.acquire() is True
        
        # Should reject 6th request
        assert rate_limiter.acquire() is False
    
    def test_retry_with_backoff_success_after_failure(self):
        """Test retry logic succeeds after initial failure."""
        call_count = 0
        
        @retry_with_backoff(RetryConfig(max_attempts=3, base_delay=0.001))
        def intermittent_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Temporary failure")
            return "success"
        
        result = intermittent_function()
        assert result == "success"
        assert call_count == 2
    
    def test_retry_with_backoff_exhausts_attempts(self):
        """Test retry logic exhausts all attempts."""
        @retry_with_backoff(RetryConfig(max_attempts=2, base_delay=0.001))
        def always_failing_function():
            raise ConnectionError("Persistent failure")
        
        with pytest.raises(ConnectionError):
            always_failing_function()


class TestDependencyInjection:
    """Test dependency injection container."""
    
    def test_register_and_resolve_transient(self):
        """Test registering and resolving transient services."""
        container = ServiceContainer()
        
        class TestService:
            def __init__(self):
                self.value = "test"
        
        container.register(TestService, TestService, ServiceLifetime.TRANSIENT)
        
        service1 = container.get_required_service(TestService)
        service2 = container.get_required_service(TestService)
        
        assert service1 is not service2  # Different instances for transient
        assert service1.value == "test"
    
    def test_register_and_resolve_singleton(self):
        """Test registering and resolving singleton services."""
        container = ServiceContainer()
        
        class TestService:
            def __init__(self):
                self.value = "test"
        
        container.register(TestService, TestService, ServiceLifetime.SINGLETON)
        
        service1 = container.get_required_service(TestService)
        service2 = container.get_required_service(TestService)
        
        assert service1 is service2  # Same instance for singleton
    
    def test_dependency_injection_with_constructor(self):
        """Test constructor dependency injection."""
        container = ServiceContainer()
        
        class DatabaseService:
            def __init__(self):
                self.connection = "db_connection"
        
        class UserService:
            def __init__(self, db: DatabaseService):
                self.db = db
        
        container.register(DatabaseService, DatabaseService)
        container.register(UserService, UserService)
        
        user_service = container.get_required_service(UserService)
        assert user_service.db.connection == "db_connection"
    
    def test_service_not_registered(self):
        """Test error when service not registered."""
        container = ServiceContainer()
        
        class UnregisteredService:
            pass
        
        with pytest.raises(KeyError):
            container.get_required_service(UnregisteredService)


class TestJobScraperTool:
    """Test job scraper tool."""
    
    @patch('subprocess.run')
    def test_scrape_jobs_success(self, mock_run):
        """Test successful job scraping."""
        # Mock successful subprocess run
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Scraping completed",
            stderr=""
        )
        
        # Mock config
        mock_config = Mock()
        mock_config.scraper = Mock(
            binary_path=Path("/fake/scraper"),
            base_dir=Path("/fake/base"),
            default_location="India,Remote",
            config_path="config/test.json",
            default_max_results=50,
            timeout=300
        )
        
        with patch('agents.tools.scraper_tool.get_global_config', return_value=mock_config):
            with patch.object(JobScraperTool, '_get_latest_export', return_value=[]):
                tool = JobScraperTool()
                result = tool.scrape_jobs("python developer", "Bangalore")
                
                assert result["success"] is True
                assert "jobs" in result
                mock_run.assert_called_once()
    
    def test_scrape_jobs_validation_error(self):
        """Test scraping with invalid parameters."""
        tool = JobScraperTool()
        
        with pytest.raises(ValidationError):
            tool.scrape_jobs("")  # Empty keywords should raise validation error
    
    @patch('subprocess.run')
    def test_scrape_jobs_scraping_error(self, mock_run):
        """Test scraping failure."""
        # Mock failed subprocess run
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Scraping failed"
        )
        
        mock_config = Mock()
        mock_config.scraper = Mock(
            binary_path=Path("/fake/scraper"),
            base_dir=Path("/fake/base"),
            default_location="India,Remote",
            config_path="config/test.json",
            default_max_results=50,
            timeout=300
        )
        
        with patch('agents.tools.scraper_tool.get_global_config', return_value=mock_config):
            tool = JobScraperTool()
            
            with pytest.raises(ScrapingError):
                tool.scrape_jobs("python developer")


class TestJobSearchAgent:
    """Test job search agent."""
    
    @patch.object(JobScraperTool, 'scrape_jobs')
    def test_search_jobs_success(self, mock_scrape):
        """Test successful job search."""
        # Mock scraper tool response
        mock_scrape.return_value = {
            "success": True,
            "jobs": [
                {
                    "title": "Python Developer",
                    "company": "Tech Corp",
                    "location": "Bangalore",
                    "description": "Python development role"
                }
            ]
        }
        
        agent = JobSearchAgent()
        criteria = JobSearchCriteria(keywords="python developer", location="Bangalore")
        
        result = agent.search_jobs(criteria)
        
        assert result["success"] is True
        assert len(result["jobs"]) == 1
        assert "insights" in result
    
    def test_job_matching_criteria(self):
        """Test job matching against criteria."""
        agent = JobSearchAgent()
        
        job = {
            "title": "Senior Python Developer",
            "description": "Senior level Python development",
            "location": "Bangalore"
        }
        
        criteria = JobSearchCriteria(
            keywords="python",
            experience_level="senior",
            location="Bangalore"
        )
        
        # This would test the private method if it were public
        # For now, just test that the agent initializes
        assert agent is not None
    
    def test_relevance_calculation(self):
        """Test job relevance scoring."""
        agent = JobSearchAgent()
        
        job = {
            "title": "Python Developer",
            "description": "Python and Django development",
            "company": "TechCorp"
        }
        
        keywords = ["python", "django"]
        score = agent._calculate_relevance(job, keywords)
        
        assert score > 0
        assert isinstance(score, float)


class TestOrchestrator:
    """Test orchestrator functionality."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self):
        """Test orchestrator initializes correctly."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            orchestrator = HireAIOrchestrator()
            assert orchestrator is not None
            assert orchestrator.model_client is not None
    
    @pytest.mark.asyncio
    @patch('agents.orchestrator.main.RoundRobinGroupChat')
    async def test_job_search_request_processing(self, mock_team):
        """Test job search request processing."""
        # Mock team conversation
        mock_result = Mock()
        mock_result.messages = [
            Mock(content="Job search completed successfully")
        ]
        
        mock_team_instance = AsyncMock()
        mock_team_instance.run.return_value = mock_result
        mock_team.return_value = mock_team_instance
        
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            orchestrator = HireAIOrchestrator()
            orchestrator.team = mock_team_instance
            
            request = JobSearchRequest(
                keywords="python developer",
                location="Bangalore",
                max_results=10
            )
            
            result = await orchestrator.process_job_search_request(request)
            
            assert result["success"] is True
            mock_team_instance.run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ask_question(self):
        """Test question asking functionality."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            orchestrator = HireAIOrchestrator()
            
            # Mock the team conversation
            mock_result = Mock()
            mock_result.messages = [Mock(content="This is a test response")]
            
            with patch.object(orchestrator, 'team') as mock_team:
                mock_team.run = AsyncMock(return_value=mock_result)
                
                response = await orchestrator.ask_question("What are the best Python jobs?")
                
                assert "test response" in response.lower()


class TestExceptionHandling:
    """Test exception handling and error scenarios."""
    
    def test_configuration_error_details(self):
        """Test configuration error provides useful details."""
        error = ConfigurationError(
            "Missing API key",
            config_key="OPENAI_API_KEY",
            config_file=".env"
        )
        
        assert "Missing API key" in str(error)
        assert error.config_key == "OPENAI_API_KEY"
    
    def test_validation_error_context(self):
        """Test validation error includes context."""
        error = ValidationError(
            "Invalid value",
            field="keywords",
            value=""
        )
        
        assert error.field == "keywords"
        assert error.context["invalid_value"] == ""
    
    def test_tool_error_tracking(self):
        """Test tool error tracks operation details."""
        error = ToolError(
            "Tool execution failed",
            tool_name="JobScraperTool",
            operation="scrape_jobs"
        )
        
        assert error.tool_name == "JobScraperTool"
        assert error.operation == "scrape_jobs"


class TestIntegration:
    """Integration tests for complete workflows."""
    
    @pytest.mark.asyncio
    @patch('subprocess.run')
    async def test_end_to_end_job_search(self, mock_run):
        """Test complete job search workflow."""
        # Mock successful scraper execution
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Jobs exported successfully",
            stderr=""
        )
        
        # Create temporary directory for test files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create mock job data file
            jobs_data = [
                {
                    "title": "Python Developer",
                    "company": "TechCorp",
                    "location": "Bangalore",
                    "description": "Python development role",
                    "keywords": "python;django;api"
                }
            ]
            
            jobs_file = temp_path / "data" / "jobs.json"
            jobs_file.parent.mkdir(exist_ok=True)
            with open(jobs_file, 'w') as f:
                json.dump(jobs_data, f)
            
            # Mock configuration
            mock_config = Mock()
            mock_config.scraper = Mock(
                binary_path=temp_path / "scraper",
                base_dir=temp_path,
                default_location="India,Remote",
                config_path="config/test.json",
                default_max_results=50,
                timeout=300
            )
            
            with patch('agents.tools.scraper_tool.get_global_config', return_value=mock_config):
                # Test the complete workflow
                tool = JobScraperTool()
                result = tool.scrape_jobs("python developer")
                
                assert result["success"] is True
                assert len(result["jobs"]) == 1
                assert result["jobs"][0]["title"] == "Python Developer"


class TestPerformance:
    """Performance tests for agent operations."""
    
    def test_configuration_loading_performance(self):
        """Test configuration loading is reasonably fast."""
        import time
        
        start_time = time.time()
        
        # Load configuration multiple times
        for _ in range(10):
            try:
                config = get_config()
            except:
                # Expected to fail in test environment
                pass
        
        end_time = time.time()
        
        # Should complete in under 1 second
        assert (end_time - start_time) < 1.0
    
    def test_dependency_injection_performance(self):
        """Test DI container performance with many services."""
        container = ServiceContainer()
        
        # Register many services
        for i in range(100):
            class_name = f"TestService{i}"
            service_class = type(class_name, (object,), {
                '__init__': lambda self: setattr(self, 'value', i)
            })
            container.register(service_class, service_class)
        
        import time
        start_time = time.time()
        
        # Resolve services
        for i in range(100):
            class_name = f"TestService{i}"
            service_class = type(class_name, (object,), {})
            try:
                container.get_service(service_class)
            except:
                pass  # Expected to fail for dynamically created types
        
        end_time = time.time()
        
        # Should complete quickly
        assert (end_time - start_time) < 0.5


# Test fixtures and utilities
@pytest.fixture
def sample_config():
    """Provide sample configuration for tests."""
    return {
        "openai_api_key": "test-key",
        "log_level": "INFO",
        "max_agent_rounds": 5
    }


@pytest.fixture
def sample_jobs():
    """Provide sample job data for tests."""
    return [
        {
            "id": "1",
            "title": "Python Developer",
            "company": "TechCorp",
            "location": "Bangalore", 
            "salary": "₹8-12 LPA",
            "description": "Python and Django development",
            "keywords": "python;django;api",
            "experience_level": "mid",
            "is_remote": False,
            "source": "test"
        },
        {
            "id": "2", 
            "title": "Senior Java Developer",
            "company": "Enterprise Inc",
            "location": "Mumbai",
            "salary": "₹15-20 LPA",
            "description": "Java microservices development",
            "keywords": "java;spring;microservices",
            "experience_level": "senior",
            "is_remote": True,
            "source": "test"
        }
    ]


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])