"""
Job Search Agent - Simplified version for job discovery and filtering
Works with the Go scraper tool to find and analyze job opportunities
"""

import json
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger
from agents.tools.scraper_tool import JobScraperTool


@dataclass
class JobSearchCriteria:
    """Criteria for job searches."""
    keywords: str
    location: str = "India,Remote"
    experience_level: Optional[str] = None
    max_results: int = 50
    remote_preference: bool = False
    min_salary: Optional[int] = None
    company_size: Optional[str] = None


class JobSearchAgent:
    """
    Simplified Job Search Agent that uses the Go scraper tool
    to find and filter job opportunities.
    """
    
    def __init__(self, llm_config: Dict[str, Any] = None):
        """Initialize the job search agent."""
        self.scraper_tool = JobScraperTool()
        self.llm_config = llm_config or {}
        logger.info("JobSearchAgent initialized")
    
    def search_jobs(self, criteria: JobSearchCriteria) -> Dict[str, Any]:
        """
        Search for jobs based on the given criteria.
        
        Args:
            criteria: JobSearchCriteria containing search parameters
            
        Returns:
            Dict containing search results and insights
        """
        try:
            logger.info(f"Starting job search: {criteria.keywords} in {criteria.location}")
            
            # Use the scraper tool to search for jobs
            scrape_result = self.scraper_tool.scrape_jobs(
                keywords=criteria.keywords,
                location=criteria.location,
                max_results=criteria.max_results
            )
            
            if not scrape_result["success"]:
                return {
                    "success": False,
                    "error": scrape_result.get("error", "Job search failed"),
                    "jobs": [],
                    "insights": {}
                }
            
            jobs = scrape_result.get("jobs", [])
            
            # Apply additional filtering based on criteria
            filtered_jobs = self._filter_jobs(jobs, criteria)
            
            # Rank jobs by relevance
            ranked_jobs = self._rank_jobs(filtered_jobs, criteria)
            
            # Generate insights
            insights = self._generate_insights(ranked_jobs, criteria)
            
            result = {
                "success": True,
                "total_found": len(jobs),
                "filtered_count": len(filtered_jobs),
                "jobs": ranked_jobs,
                "insights": insights
            }
            
            logger.info(f"Job search completed: {len(ranked_jobs)} final results")
            return result
            
        except Exception as e:
            logger.error(f"Job search failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "jobs": [],
                "insights": {}
            }
    
    def _filter_jobs(self, jobs: List[Dict], criteria: JobSearchCriteria) -> List[Dict]:
        """Apply additional filtering to job results."""
        filtered = []
        
        for job in jobs:
            # Basic filtering logic
            if self._job_matches_criteria(job, criteria):
                filtered.append(job)
        
        return filtered
    
    def _job_matches_criteria(self, job: Dict, criteria: JobSearchCriteria) -> bool:
        """Check if a job matches the search criteria."""
        title = job.get("title", "").lower()
        description = job.get("description", "").lower()
        location = job.get("location", "").lower()
        
        # Experience level filtering
        if criteria.experience_level:
            exp_level = criteria.experience_level.lower()
            if exp_level == "junior" and any(word in title for word in ["senior", "lead", "principal"]):
                return False
            elif exp_level == "senior" and any(word in title for word in ["junior", "intern", "entry"]):
                return False
        
        # Remote preference
        if criteria.remote_preference:
            if not any(word in location for word in ["remote", "work from home", "wfh"]):
                return False
        
        return True
    
    def _rank_jobs(self, jobs: List[Dict], criteria: JobSearchCriteria) -> List[Dict]:
        """Rank jobs by relevance to search criteria."""
        keywords = criteria.keywords.lower().split(",")
        keywords = [k.strip() for k in keywords]
        
        for job in jobs:
            relevance_score = self._calculate_relevance(job, keywords)
            job["relevance"] = relevance_score
            job["search_rank"] = 0  # Will be set after sorting
        
        # Sort by relevance score
        sorted_jobs = sorted(jobs, key=lambda x: x.get("relevance", 0), reverse=True)
        
        # Set rank
        for i, job in enumerate(sorted_jobs):
            job["search_rank"] = i + 1
        
        return sorted_jobs
    
    def _calculate_relevance(self, job: Dict, keywords: List[str]) -> float:
        """Calculate relevance score for a job."""
        title = job.get("title", "").lower()
        description = job.get("description", "").lower()
        company = job.get("company", "").lower()
        
        score = 0.0
        
        for keyword in keywords:
            # Title matches are most important
            if keyword in title:
                score += 3.0
            
            # Description matches
            if keyword in description:
                score += 1.0
            
            # Company matches
            if keyword in company:
                score += 0.5
        
        # Normalize by number of keywords
        if keywords:
            score = score / len(keywords)
        
        return score
    
    def _generate_insights(self, jobs: List[Dict], criteria: JobSearchCriteria) -> Dict[str, Any]:
        """Generate insights from the job search results."""
        if not jobs:
            return {}
        
        insights = {}
        
        # Top companies
        companies = {}
        for job in jobs:
            company = job.get("company", "Unknown")
            companies[company] = companies.get(company, 0) + 1
        
        insights["top_companies"] = dict(sorted(companies.items(), key=lambda x: x[1], reverse=True))
        
        # Popular skills (extracted from titles and descriptions)
        skills = {}
        skill_keywords = [
            "python", "java", "javascript", "react", "node", "angular", "vue",
            "docker", "kubernetes", "aws", "azure", "gcp", "sql", "mongodb",
            "machine learning", "ai", "data science", "devops", "microservices"
        ]
        
        for job in jobs:
            text = f"{job.get('title', '')} {job.get('description', '')}".lower()
            for skill in skill_keywords:
                if skill in text:
                    skills[skill] = skills.get(skill, 0) + 1
        
        insights["popular_skills"] = dict(sorted(skills.items(), key=lambda x: x[1], reverse=True))
        
        # Location distribution
        locations = {}
        for job in jobs:
            location = job.get("location", "Unknown")
            locations[location] = locations.get(location, 0) + 1
        
        insights["location_distribution"] = dict(sorted(locations.items(), key=lambda x: x[1], reverse=True))
        
        # Basic recommendations
        recommendations = []
        
        if len(jobs) < 10:
            recommendations.append("Consider broadening your search keywords for more opportunities")
        
        if criteria.experience_level == "junior" and any("senior" in job.get("title", "").lower() for job in jobs[:5]):
            recommendations.append("Many results show senior roles - consider highlighting transferable skills")
        
        top_skill = max(skills.items(), key=lambda x: x[1])[0] if skills else None
        if top_skill:
            recommendations.append(f"'{top_skill}' appears frequently - consider emphasizing this skill")
        
        insights["recommendations"] = recommendations
        
        return insights