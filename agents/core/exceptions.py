"""
Custom exceptions for the Hire.AI agentic system.

This module defines custom exceptions that provide better error handling
and debugging capabilities throughout the application.
"""

from typing import Optional, Any, Dict


class HireAIError(Exception):
    """Base exception class for all Hire.AI related errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def __str__(self) -> str:
        base_msg = self.message
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{base_msg} (Details: {details_str})"
        return base_msg


class ScrapingError(HireAIError):
    """Raised when job scraping operations fail."""
    
    def __init__(self, message: str, source: Optional[str] = None, 
                 error_code: Optional[str] = None, **kwargs):
        details = {"source": source, "error_code": error_code, **kwargs}
        super().__init__(message, {k: v for k, v in details.items() if v is not None})


class AgentError(HireAIError):
    """Raised when AI agent operations fail."""
    
    def __init__(self, message: str, agent_name: Optional[str] = None,
                 operation: Optional[str] = None, **kwargs):
        details = {"agent_name": agent_name, "operation": operation, **kwargs}
        super().__init__(message, {k: v for k, v in details.items() if v is not None})


class ConfigurationError(HireAIError):
    """Raised when configuration is invalid or missing."""
    
    def __init__(self, message: str, config_key: Optional[str] = None,
                 config_file: Optional[str] = None, **kwargs):
        details = {"config_key": config_key, "config_file": config_file, **kwargs}
        super().__init__(message, {k: v for k, v in details.items() if v is not None})


class ToolError(HireAIError):
    """Raised when tool operations fail."""
    
    def __init__(self, message: str, tool_name: Optional[str] = None,
                 operation: Optional[str] = None, **kwargs):
        details = {"tool_name": tool_name, "operation": operation, **kwargs}
        super().__init__(message, {k: v for k, v in details.items() if v is not None})


class ValidationError(HireAIError):
    """Raised when data validation fails."""
    
    def __init__(self, message: str, field: Optional[str] = None,
                 value: Optional[Any] = None, **kwargs):
        details = {"field": field, "value": value, **kwargs}
        super().__init__(message, {k: v for k, v in details.items() if v is not None})


class CircuitBreakerError(HireAIError):
    """Raised when circuit breaker is open."""
    
    def __init__(self, message: str = "Circuit breaker is open", 
                 service_name: Optional[str] = None, **kwargs):
        details = {"service_name": service_name, **kwargs}
        super().__init__(message, {k: v for k, v in details.items() if v is not None})


class RetryableError(HireAIError):
    """Base class for errors that can be retried."""
    
    def __init__(self, message: str, retry_after: Optional[int] = None,
                 max_retries: Optional[int] = None, **kwargs):
        details = {"retry_after": retry_after, "max_retries": max_retries, 
                  "retryable": True, **kwargs}
        super().__init__(message, {k: v for k, v in details.items() if v is not None})


class RateLimitError(RetryableError):
    """Raised when rate limits are exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded", 
                 retry_after: int = 60, **kwargs):
        super().__init__(message, retry_after=retry_after, **kwargs)


class TimeoutError(RetryableError):
    """Raised when operations timeout."""
    
    def __init__(self, message: str, timeout_duration: Optional[int] = None, **kwargs):
        details = {"timeout_duration": timeout_duration, **kwargs}
        super().__init__(message, context=details, **kwargs)


class ExternalServiceError(RetryableError):
    """Raised when external service calls fail."""
    
    def __init__(self, message: str, service_name: Optional[str] = None,
                 status_code: Optional[int] = None, **kwargs):
        details = {"service_name": service_name, "status_code": status_code, **kwargs}
        super().__init__(message, context=details, **kwargs)