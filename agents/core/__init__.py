"""
Core functionality for Hire.AI agents.

This module provides the base classes, configurations, and utilities
that are shared across all AI agents in the system.
"""

from .exceptions import HireAIError, ScrapingError, AgentError, ConfigurationError, ToolError, ValidationError
from .config import AgentConfig, ScraperConfig, get_config, get_global_config
from .logging_config import setup_logging, get_logger

__all__ = [
    'HireAIError',
    'ScrapingError', 
    'AgentError',
    'ConfigurationError',
    'ToolError',
    'ValidationError',
    'AgentConfig',
    'ScraperConfig',
    'get_config',
    'get_global_config',
    'setup_logging',
    'get_logger'
]