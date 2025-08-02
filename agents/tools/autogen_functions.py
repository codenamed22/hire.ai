"""
AutoGen-compatible function registrations for Hire.AI tools.

This module provides function registrations that can be used with AutoGen agents
for accessing database search and hybrid search capabilities.
"""

from typing import Dict, Any, List
from agents.tools.database_search_tool import search_database_jobs
from agents.tools.hybrid_search_tool import hybrid_job_search


def search_jobs_database(keywords: str, location: str = None, max_results: int = 25) -> Dict[str, Any]:
    """
    Search for jobs in the Hire.AI database.
    
    This function searches the stored job database for opportunities matching
    the specified keywords and location. It's fast but limited to previously
    scraped jobs.
    
    Args:
        keywords: Comma-separated job search keywords (e.g., "python, django, api")
        location: Optional location filter (e.g., "Bangalore", "Remote", "India")
        max_results: Maximum number of results to return (default: 25)
    
    Returns:
        Dictionary containing:
        - success: Boolean indicating if search was successful
        - jobs: List of job dictionaries with title, company, location, etc.
        - total_found: Number of jobs found
        - insights: Analysis of search results including top companies and locations
        - search_terms: Keywords that were searched
    """
    return search_database_jobs(keywords, location, max_results)


def search_jobs_hybrid(keywords: str, location: str = None, max_results: int = 50, 
                      include_scraping: bool = True) -> Dict[str, Any]:
    """
    Perform hybrid job search combining database and live scraping.
    
    This function first searches the database for existing jobs, then optionally
    performs live scraping if insufficient results are found. Provides the most
    comprehensive job search experience.
    
    Args:
        keywords: Comma-separated job search keywords (e.g., "react, frontend, javascript")
        location: Optional location filter (e.g., "Mumbai", "Remote", "India")
        max_results: Maximum number of results to return (default: 50)
        include_scraping: Whether to perform live scraping if needed (default: True)
    
    Returns:
        Dictionary containing:
        - success: Boolean indicating if search was successful
        - jobs: List of job dictionaries with title, company, location, etc.
        - total_found: Total number of jobs found
        - database_count: Number of jobs from database
        - scraping_count: Number of jobs from live scraping
        - scraping_triggered: Whether live scraping was performed
        - insights: Comprehensive analysis including source distribution
        - performance: Search performance metrics
    """
    return hybrid_job_search(keywords, location, max_results, include_scraping)


def get_job_search_recommendations(user_profile: str = None, experience_level: str = None) -> Dict[str, Any]:
    """
    Get personalized job search recommendations based on user profile.
    
    Args:
        user_profile: User's skills and interests (e.g., "Python developer with 3 years experience")
        experience_level: Experience level (e.g., "junior", "mid", "senior")
    
    Returns:
        Dictionary with search recommendations and suggested keywords
    """
    recommendations = {
        "success": True,
        "recommended_keywords": [],
        "search_strategy": "hybrid",
        "tips": []
    }
    
    # Basic recommendations based on experience level
    if experience_level == "junior":
        recommendations["recommended_keywords"] = ["junior", "entry level", "trainee", "graduate"]
        recommendations["tips"] = [
            "Focus on entry-level positions and internships",
            "Highlight relevant projects and coursework",
            "Consider remote opportunities for broader reach"
        ]
    elif experience_level == "senior":
        recommendations["recommended_keywords"] = ["senior", "lead", "architect", "principal"]
        recommendations["tips"] = [
            "Target leadership and senior technical roles",
            "Emphasize team leadership and project management experience",
            "Look for opportunities to mentor junior developers"
        ]
    else:
        recommendations["recommended_keywords"] = ["developer", "engineer", "specialist"]
        recommendations["tips"] = [
            "Focus on roles matching your technical skills",
            "Consider both individual contributor and team lead positions",
            "Expand search to include related technologies"
        ]
    
    # Add profile-based recommendations
    if user_profile:
        profile_lower = user_profile.lower()
        if "python" in profile_lower:
            recommendations["recommended_keywords"].extend(["python", "django", "flask", "fastapi"])
        if "javascript" in profile_lower or "js" in profile_lower:
            recommendations["recommended_keywords"].extend(["javascript", "react", "node", "vue"])
        if "java" in profile_lower:
            recommendations["recommended_keywords"].extend(["java", "spring", "maven", "gradle"])
        if "data" in profile_lower:
            recommendations["recommended_keywords"].extend(["data science", "machine learning", "analytics"])
        if "devops" in profile_lower:
            recommendations["recommended_keywords"].extend(["devops", "kubernetes", "docker", "aws"])
    
    # Remove duplicates and limit keywords
    recommendations["recommended_keywords"] = list(set(recommendations["recommended_keywords"]))[:10]
    
    return recommendations


# Function registry for AutoGen agents
AUTOGEN_FUNCTION_REGISTRY = {
    "search_jobs_database": {
        "function": search_jobs_database,
        "description": "Search for jobs in the Hire.AI database (fast, cached results)",
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "Comma-separated job search keywords"
                },
                "location": {
                    "type": "string",
                    "description": "Location filter (optional)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 25)"
                }
            },
            "required": ["keywords"]
        }
    },
    
    "search_jobs_hybrid": {
        "function": search_jobs_hybrid,
        "description": "Hybrid job search combining database and live scraping (comprehensive)",
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "Comma-separated job search keywords"
                },
                "location": {
                    "type": "string",
                    "description": "Location filter (optional)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 50)"
                },
                "include_scraping": {
                    "type": "boolean",
                    "description": "Whether to perform live scraping if needed (default: true)"
                }
            },
            "required": ["keywords"]
        }
    },
    
    "get_job_search_recommendations": {
        "function": get_job_search_recommendations,
        "description": "Get personalized job search recommendations and keyword suggestions",
        "parameters": {
            "type": "object",
            "properties": {
                "user_profile": {
                    "type": "string",
                    "description": "User's skills and background (optional)"
                },
                "experience_level": {
                    "type": "string",
                    "description": "Experience level: junior, mid, or senior (optional)"
                }
            },
            "required": []
        }
    }
}


def get_available_functions() -> List[str]:
    """Get list of available AutoGen function names."""
    return list(AUTOGEN_FUNCTION_REGISTRY.keys())


def get_function_definitions() -> List[Dict[str, Any]]:
    """Get function definitions in AutoGen format."""
    definitions = []
    for name, config in AUTOGEN_FUNCTION_REGISTRY.items():
        definitions.append({
            "name": name,
            "description": config["description"],
            "parameters": config["parameters"]
        })
    return definitions


def execute_function(function_name: str, **kwargs) -> Dict[str, Any]:
    """Execute a registered function by name."""
    if function_name not in AUTOGEN_FUNCTION_REGISTRY:
        return {
            "success": False,
            "error": f"Function '{function_name}' not found",
            "available_functions": get_available_functions()
        }
    
    try:
        func = AUTOGEN_FUNCTION_REGISTRY[function_name]["function"]
        return func(**kwargs)
    except Exception as e:
        return {
            "success": False,
            "error": f"Function execution failed: {str(e)}"
        }