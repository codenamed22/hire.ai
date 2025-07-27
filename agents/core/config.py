"""
Configuration management for Hire.AI agents.

This module provides centralized configuration management with validation,
type checking, and environment variable support.
"""

import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from .exceptions import ConfigurationError


@dataclass
class OpenAIConfig:
    """Configuration for OpenAI API."""
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout: int = 300
    max_retries: int = 3

    def __post_init__(self):
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            raise ConfigurationError(
                "OpenAI API key is required", 
                config_key="OPENAI_API_KEY"
            )


@dataclass
class ScraperConfig:
    """Configuration for the Go scraper integration."""
    binary_path: Path
    base_dir: Path
    config_path: str = "config/production.json"
    default_keywords: str = "software engineer,developer,programmer"
    default_location: str = "India,Remote"
    default_max_results: int = 50
    timeout: int = 300

    def __post_init__(self):
        if not self.binary_path.exists():
            raise ConfigurationError(
                f"Scraper binary not found at {self.binary_path}",
                config_key="binary_path"
            )


@dataclass 
class AgentConfig:
    """Main configuration for all agents."""
    openai: OpenAIConfig
    scraper: ScraperConfig
    
    # Agent-specific settings
    orchestrator_model: str = "gpt-4o-mini"
    job_search_agent_model: str = "gpt-4o-mini"
    job_analyzer_model: str = "gpt-4o-mini"
    career_advisor_model: str = "gpt-4o-mini"
    
    max_agent_rounds: int = 10
    agent_timeout: int = 300
    
    # Logging settings
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/agents.log"
    
    # Storage settings
    data_dir: str = "data"
    exports_dir: str = "exports"
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_log_levels:
            raise ConfigurationError(
                f"Invalid log level: {self.log_level}. Must be one of {valid_log_levels}",
                config_key="LOG_LEVEL"
            )
        
        if self.max_agent_rounds < 1:
            raise ConfigurationError(
                "max_agent_rounds must be at least 1",
                config_key="MAX_AGENT_ROUNDS"
            )


def _load_env_file(env_file: Optional[str] = None) -> None:
    """Load environment variables from .env file."""
    if env_file is None:
        env_file = ".env.agents"
    
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # Try to find it in parent directories
        current_dir = Path.cwd()
        for parent in [current_dir] + list(current_dir.parents):
            env_path = parent / env_file
            if env_path.exists():
                load_dotenv(env_path)
                break


def get_config(env_file: Optional[str] = None) -> AgentConfig:
    """
    Get the application configuration.
    
    Args:
        env_file: Optional path to environment file
        
    Returns:
        AgentConfig: Validated configuration object
        
    Raises:
        ConfigurationError: If configuration is invalid or missing
    """
    # Load environment variables
    _load_env_file(env_file)
    
    # Get project root (where the binary should be)
    project_root = Path.cwd()
    if (project_root / "bin" / "job-scraper").exists():
        binary_path = project_root / "bin" / "job-scraper"
        base_dir = project_root
    else:
        # Try to find project root by looking for go.mod
        for parent in [project_root] + list(project_root.parents):
            if (parent / "go.mod").exists():
                binary_path = parent / "bin" / "job-scraper"
                base_dir = parent
                break
        else:
            raise ConfigurationError(
                "Could not find project root or scraper binary",
                config_key="binary_path"
            )
    
    try:
        # Create OpenAI configuration
        openai_config = OpenAIConfig(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            timeout=int(os.getenv("AGENT_TIMEOUT", "300")),
            max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "3"))
        )
        
        # Create scraper configuration
        scraper_config = ScraperConfig(
            binary_path=binary_path,
            base_dir=base_dir,
            config_path=os.getenv("SCRAPER_CONFIG_PATH", "config/production.json"),
            default_keywords=os.getenv("DEFAULT_KEYWORDS", "software engineer,developer,programmer"),
            default_location=os.getenv("DEFAULT_LOCATION", "India,Remote"),
            default_max_results=int(os.getenv("DEFAULT_MAX_RESULTS", "50")),
            timeout=int(os.getenv("SCRAPER_TIMEOUT", "300"))
        )
        
        # Create main agent configuration
        config = AgentConfig(
            openai=openai_config,
            scraper=scraper_config,
            orchestrator_model=os.getenv("ORCHESTRATOR_MODEL", "gpt-4o-mini"),
            job_search_agent_model=os.getenv("JOB_SEARCH_AGENT_MODEL", "gpt-4o-mini"),
            job_analyzer_model=os.getenv("JOB_ANALYZER_MODEL", "gpt-4o-mini"),
            career_advisor_model=os.getenv("CAREER_ADVISOR_MODEL", "gpt-4o-mini"),
            max_agent_rounds=int(os.getenv("MAX_AGENT_ROUNDS", "10")),
            agent_timeout=int(os.getenv("AGENT_TIMEOUT", "300")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_file=os.getenv("LOG_FILE", "logs/agents.log"),
            data_dir=os.getenv("DATA_DIR", "data"),
            exports_dir=os.getenv("EXPORTS_DIR", "exports")
        )
        
        return config
        
    except ValueError as e:
        raise ConfigurationError(f"Invalid configuration value: {str(e)}") from e
    except Exception as e:
        raise ConfigurationError(f"Failed to load configuration: {str(e)}") from e


# Global configuration instance
_config: Optional[AgentConfig] = None


def get_global_config() -> AgentConfig:
    """Get the global configuration instance (singleton pattern)."""
    global _config
    if _config is None:
        _config = get_config()
    return _config


def reset_global_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None