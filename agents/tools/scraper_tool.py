"""
Job Scraper Tool - Integration between Python agents and Go scraper.

This module provides a robust interface for Python AI agents to interact
with the Go-based job scraper, handling errors, data validation, and 
providing structured responses.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import pandas as pd
from datetime import datetime

from agents.core.exceptions import (
    ToolError, ValidationError, ScrapingError
)
from agents.core.config import get_global_config
from agents.core.logging_config import get_logger
from agents.core.resilience import (
    retry_with_backoff, RetryConfig, timeout,
    resilient_external_service
)
from agents.core.dependency_injection import injectable

logger = get_logger(__name__)


@injectable
class JobScraperTool:
    """
    Tool for integrating Python agents with the Go job scraper.
    
    This class provides methods to:
    - Execute job searches using the Go binary
    - Export existing job data
    - Analyze and process job data
    - Handle errors and validation
    """
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize the job scraper tool.
        
        Args:
            config: Optional configuration object. If None, uses global config.
        """
        if config is None:
            config = get_global_config()
        
        self.config = config.scraper
        self.binary_path = self.config.binary_path
        self.base_dir = self.config.base_dir
        
        logger.info(f"JobScraperTool initialized with binary: {self.binary_path}")
        self._validate_setup()

    def _validate_setup(self) -> None:
        """Validate that the scraper setup is correct."""
        if not self.binary_path.exists():
            raise ToolError(
                f"Job scraper binary not found at {self.binary_path}",
                tool_name="JobScraperTool",
                operation="initialization"
            )
        
        if not self.binary_path.is_file():
            raise ToolError(
                f"Path {self.binary_path} is not a file",
                tool_name="JobScraperTool", 
                operation="initialization"
            )

    @retry_with_backoff(RetryConfig(
        max_attempts=3,
        base_delay=2.0,
        retryable_exceptions=(ScrapingError, subprocess.TimeoutExpired)
    ))
    @timeout(300)  # 5 minute timeout
    def scrape_jobs(
        self,
        keywords: str,
        location: str = None,
        config: str = None,
        max_results: int = None,
        timeout_seconds: int = None
    ) -> Dict[str, Any]:
        """
        Execute a job search using the Go scraper.
        
        Args:
            keywords: Comma-separated job search keywords
            location: Job location (default from config)
            config: Configuration file path (default from config) 
            max_results: Maximum number of results (default from config)
            timeout: Timeout in seconds (default from config)
            
        Returns:
            Dict containing:
                - success: bool
                - jobs: List of job dictionaries
                - total_found: int
                - error: str (if success=False)
                
        Raises:
            ValidationError: If input parameters are invalid
            ScrapingError: If scraping operation fails
        """
        # Validate inputs
        if not keywords or not keywords.strip():
            raise ValidationError("Keywords cannot be empty", field="keywords")
        
        # Use defaults from config if not provided
        location = location or self.config.default_location
        config_path = config or self.config.config_path
        max_results = max_results or self.config.default_max_results
        timeout_val = timeout_seconds or self.config.timeout
        
        logger.info(f"Starting job scraping: keywords='{keywords}', location='{location}'")
        
        try:
            # Build command
            cmd = [
                str(self.binary_path),
                "-keywords", keywords,
                "-location", location,
                "-config", config_path,
                "-verbose"
            ]
            
            # Execute the command
            result = subprocess.run(
                cmd,
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=timeout_val
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown scraping error"
                raise ScrapingError(
                    f"Scraping failed: {error_msg}",
                    source="go_scraper",
                    error_code=str(result.returncode)
                )
            
            # Get the scraped data
            jobs = self._get_latest_export()
            total_found = len(jobs)
            
            logger.info(f"Scraping completed: {total_found} jobs found")
            
            return {
                "success": True,
                "jobs": jobs,
                "total_found": total_found,
                "keywords": keywords,
                "location": location,
                "scraped_at": datetime.now().isoformat()
            }
            
        except subprocess.TimeoutExpired:
            raise ScrapingError(
                f"Scraping timed out after {timeout} seconds",
                source="go_scraper",
                operation="scrape_jobs"
            )
        except FileNotFoundError:
            raise ToolError(
                f"Scraper binary not found: {self.binary_path}",
                tool_name="JobScraperTool",
                operation="scrape_jobs"
            )
        except Exception as e:
            raise ScrapingError(
                f"Unexpected error during scraping: {str(e)}",
                source="go_scraper",
                operation="scrape_jobs"
            ) from e

    def export_jobs(self, format_type: str = "json", filename: str = None) -> Dict[str, Any]:
        """
        Export existing job data to file.
        
        Args:
            format_type: Export format ("json" or "csv")
            filename: Custom filename (optional)
            
        Returns:
            Dict containing:
                - success: bool
                - file_path: str (if success=True)
                - error: str (if success=False)
                
        Raises:
            ValidationError: If format_type is invalid
            ToolError: If export operation fails
        """
        if format_type not in ["json", "csv"]:
            raise ValidationError(
                f"Invalid format: {format_type}. Must be 'json' or 'csv'",
                field="format_type"
            )
        
        logger.info(f"Exporting jobs to {format_type} format")
        
        try:
            cmd = [str(self.binary_path), "-export", format_type]
            if filename:
                cmd.extend(["-export-file", filename])
                
            result = subprocess.run(
                cmd,
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Export failed"
                return {
                    "success": False,
                    "error": error_msg
                }
            
            # Extract file path from output if available
            output_lines = result.stdout.strip().split('\n')
            file_path = None
            for line in output_lines:
                if "exported to" in line.lower():
                    # Try to extract file path
                    parts = line.split()
                    if parts:
                        file_path = parts[-1]
                    break
            
            return {
                "success": True,
                "file_path": file_path,
                "format": format_type
            }
            
        except Exception as e:
            raise ToolError(
                f"Export operation failed: {str(e)}",
                tool_name="JobScraperTool",
                operation="export_jobs"
            ) from e

    def _get_latest_export(self) -> List[Dict[str, Any]]:
        """
        Get the latest exported job data.
        
        Returns:
            List of job dictionaries
            
        Raises:
            ToolError: If no data file is found or data is invalid
        """
        try:
            # Try to find the latest jobs data file
            data_files = [
                self.base_dir / "data" / "jobs.json",
                self.base_dir / "exports" / "latest_jobs.json"
            ]
            
            jobs_data = None
            for data_file in data_files:
                if data_file.exists():
                    try:
                        with open(data_file, 'r', encoding='utf-8') as f:
                            jobs_data = json.load(f)
                        break
                    except (json.JSONDecodeError, IOError):
                        continue
            
            if jobs_data is None:
                # Try to find any export file
                exports_dir = self.base_dir / "exports"
                if exports_dir.exists():
                    json_files = list(exports_dir.glob("jobs_export_*.json"))
                    if json_files:
                        # Get the most recent file
                        latest_file = max(json_files, key=lambda p: p.stat().st_mtime)
                        try:
                            with open(latest_file, 'r', encoding='utf-8') as f:
                                jobs_data = json.load(f)
                        except (json.JSONDecodeError, IOError):
                            pass
            
            if jobs_data is None:
                logger.warning("No job data found")
                return []
            
            # Ensure it's a list
            if isinstance(jobs_data, dict):
                jobs_data = jobs_data.get('jobs', [])
            elif not isinstance(jobs_data, list):
                logger.warning(f"Unexpected data format: {type(jobs_data)}")
                return []
            
            logger.debug(f"Loaded {len(jobs_data)} jobs from data file")
            return jobs_data
            
        except Exception as e:
            logger.error(f"Error loading job data: {str(e)}")
            return []

    def analyze_jobs(self, jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze job data and provide insights.
        
        Args:
            jobs: List of job dictionaries
            
        Returns:
            Dict containing analysis results
            
        Raises:
            ValidationError: If jobs data is invalid
        """
        if not isinstance(jobs, list):
            raise ValidationError("Jobs must be a list", field="jobs")
        
        if not jobs:
            return {
                "total_jobs": 0,
                "analysis_date": datetime.now().isoformat(),
                "message": "No jobs to analyze"
            }
        
        try:
            # Convert to DataFrame for analysis
            df = pd.DataFrame(jobs)
            
            analysis = {
                "total_jobs": len(jobs),
                "analysis_date": datetime.now().isoformat(),
                "unique_companies": df['company'].nunique() if 'company' in df.columns else 0,
                "unique_locations": df['location'].nunique() if 'location' in df.columns else 0,
            }
            
            # Top companies
            if 'company' in df.columns:
                top_companies = df['company'].value_counts().head(10).to_dict()
                analysis['top_companies'] = top_companies
            
            # Top locations  
            if 'location' in df.columns:
                top_locations = df['location'].value_counts().head(10).to_dict()
                analysis['top_locations'] = top_locations
            
            # Keywords analysis
            if 'keywords' in df.columns:
                all_keywords = []
                for keywords_str in df['keywords'].dropna():
                    if isinstance(keywords_str, str):
                        keywords = [k.strip() for k in keywords_str.split(';')]
                        all_keywords.extend(keywords)
                
                if all_keywords:
                    keyword_counts = pd.Series(all_keywords).value_counts().head(15).to_dict()
                    analysis['top_keywords'] = keyword_counts
            
            # Source analysis
            if 'source' in df.columns:
                source_counts = df['source'].value_counts().to_dict()
                analysis['sources'] = source_counts
            
            logger.debug(f"Analysis completed for {len(jobs)} jobs")
            return analysis
            
        except Exception as e:
            raise ToolError(
                f"Job analysis failed: {str(e)}",
                tool_name="JobScraperTool",
                operation="analyze_jobs"
            ) from e

    def get_job_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about available job data.
        
        Returns:
            Dict containing job statistics
        """
        try:
            jobs = self._get_latest_export()
            return self.analyze_jobs(jobs)
        except Exception as e:
            logger.error(f"Failed to get job statistics: {str(e)}")
            return {
                "total_jobs": 0,
                "error": str(e),
                "analysis_date": datetime.now().isoformat()
            }


# AutoGen-compatible functions for use with AI agents
def scrape_jobs_function(
    keywords: str, 
    location: str = "India,Remote",
    max_results: int = 50
) -> str:
    """
    AutoGen-compatible function for job scraping.
    
    Args:
        keywords: Job search keywords
        location: Job location
        max_results: Maximum results
        
    Returns:
        JSON string with results
    """
    try:
        tool = JobScraperTool()
        result = tool.scrape_jobs(keywords, location, max_results=max_results)
        return json.dumps(result, indent=2)
    except Exception as e:
        error_result = {
            "success": False,
            "error": str(e),
            "operation": "scrape_jobs"
        }
        return json.dumps(error_result, indent=2)


def analyze_jobs_function() -> str:
    """
    AutoGen-compatible function for job analysis.
    
    Returns:
        JSON string with analysis results
    """
    try:
        tool = JobScraperTool()
        analysis = tool.get_job_statistics()
        return json.dumps(analysis, indent=2)
    except Exception as e:
        error_result = {
            "error": str(e),
            "operation": "analyze_jobs"
        }
        return json.dumps(error_result, indent=2)


def export_jobs_function(format_type: str = "json") -> str:
    """
    AutoGen-compatible function for job export.
    
    Args:
        format_type: Export format ("json" or "csv")
        
    Returns:
        JSON string with export results
    """
    try:
        tool = JobScraperTool()
        result = tool.export_jobs(format_type)
        return json.dumps(result, indent=2)
    except Exception as e:
        error_result = {
            "success": False,
            "error": str(e),
            "operation": "export_jobs"
        }
        return json.dumps(error_result, indent=2)