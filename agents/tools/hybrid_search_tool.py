"""
Hybrid search tool that combines database search with live scraping.

This tool provides intelligent job search by first checking the database for existing jobs,
then optionally performing live scraping to find additional opportunities.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from agents.core.dependency_injection import injectable
from agents.tools.database_search_tool import DatabaseSearchTool
from agents.tools.scraper_tool import JobScraperTool


@dataclass
class HybridSearchRequest:
    keywords: List[str]
    location: Optional[str] = None
    max_results: int = 50
    include_scraping: bool = True
    scrape_threshold: int = 10  # If database has fewer than this, trigger scraping
    max_scrape_results: int = 20


@injectable
class HybridSearchTool:
    """Tool that combines database search with live scraping for comprehensive job search."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.db_tool = DatabaseSearchTool()
        self.scraper_tool = JobScraperTool()
    
    def search_jobs_intelligently(self, request: HybridSearchRequest) -> Dict[str, Any]:
        """
        Perform intelligent hybrid search combining database and live scraping.
        
        Args:
            request: HybridSearchRequest with search parameters
            
        Returns:
            Dictionary with combined search results and metadata
        """
        start_time = datetime.now()
        
        try:
            # Step 1: Search existing database
            self.logger.info(f"Searching database for keywords: {request.keywords}")
            db_result = self.db_tool.intelligent_search(
                keywords=request.keywords,
                location=request.location,
                max_results=request.max_results
            )
            
            db_jobs = db_result.get("jobs", [])
            db_count = len(db_jobs)
            
            self.logger.info(f"Found {db_count} jobs in database")
            
            # Step 2: Determine if scraping is needed
            should_scrape = (
                request.include_scraping and 
                db_count < request.scrape_threshold
            )
            
            scraping_jobs = []
            scraping_error = None
            
            if should_scrape:
                self.logger.info("Database results below threshold, initiating live scraping")
                try:
                    keywords_str = " ".join(request.keywords)
                    scrape_result = self.scraper_tool.scrape_jobs(
                        keywords=keywords_str,
                        location=request.location or "India,Remote",
                        max_results=request.max_scrape_results
                    )
                    
                    if scrape_result.get("success"):
                        scraping_jobs = scrape_result.get("jobs", [])
                        self.logger.info(f"Scraped {len(scraping_jobs)} additional jobs")
                    else:
                        scraping_error = scrape_result.get("error")
                        self.logger.warning(f"Scraping failed: {scraping_error}")
                        
                except Exception as e:
                    scraping_error = str(e)
                    self.logger.error(f"Scraping error: {e}")
            
            # Step 3: Combine and deduplicate results
            combined_jobs = self._combine_and_rank_jobs(db_jobs, scraping_jobs, request.keywords)
            
            # Step 4: Limit to requested max results
            if len(combined_jobs) > request.max_results:
                combined_jobs = combined_jobs[:request.max_results]
            
            # Step 5: Generate comprehensive insights
            insights = self._generate_hybrid_insights(
                db_jobs, scraping_jobs, combined_jobs, request.keywords, should_scrape
            )
            
            # Performance metrics
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            return {
                "success": True,
                "jobs": combined_jobs,
                "total_found": len(combined_jobs),
                "database_count": db_count,
                "scraping_count": len(scraping_jobs),
                "scraping_triggered": should_scrape,
                "scraping_error": scraping_error,
                "insights": insights,
                "search_strategy": "hybrid",
                "performance": {
                    "duration_seconds": duration,
                    "database_search_time": "< 1s",
                    "scraping_triggered": should_scrape
                },
                "search_terms": request.keywords,
                "location_filter": request.location
            }
            
        except Exception as e:
            self.logger.error(f"Hybrid search failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "jobs": [],
                "total_found": 0,
                "search_strategy": "hybrid"
            }
    
    def _combine_and_rank_jobs(self, db_jobs: List[Dict], scraping_jobs: List[Dict], 
                              keywords: List[str]) -> List[Dict]:
        """Combine database and scraped jobs, removing duplicates and ranking by relevance."""
        combined = []
        seen_jobs = set()
        
        # Add database jobs first (they're already stored and processed)
        for job in db_jobs:
            job_key = self._generate_job_key(job)
            if job_key not in seen_jobs:
                job["source_type"] = "database"
                combined.append(job)
                seen_jobs.add(job_key)
        
        # Add scraped jobs, avoiding duplicates
        for job in scraping_jobs:
            job_key = self._generate_job_key(job)
            if job_key not in seen_jobs:
                job["source_type"] = "live_scraping"
                # Calculate relevance for scraped jobs
                job["relevance_score"] = self._calculate_relevance(job, keywords)
                combined.append(job)
                seen_jobs.add(job_key)
        
        # Sort by relevance score (higher is better)
        combined.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        return combined
    
    def _generate_job_key(self, job: Dict) -> str:
        """Generate a unique key for job deduplication."""
        title = job.get("title", "").lower().strip()
        company = job.get("company", "").lower().strip()
        location = job.get("location", "").lower().strip()
        return f"{title}|{company}|{location}"
    
    def _calculate_relevance(self, job: Dict, keywords: List[str]) -> float:
        """Calculate relevance score for a job based on keywords."""
        score = 0.0
        
        # Get job text fields
        title = job.get("title", "").lower()
        description = job.get("description", "").lower()
        company = job.get("company", "").lower()
        
        # Calculate keyword matches
        for keyword in keywords:
            keyword_lower = keyword.lower()
            
            # Title matches are worth more
            if keyword_lower in title:
                score += 3.0
            
            # Description matches
            if keyword_lower in description:
                score += 1.5
            
            # Company matches
            if keyword_lower in company:
                score += 1.0
        
        # Bonus for recent jobs (if timestamp available)
        if job.get("created_at"):
            try:
                if isinstance(job["created_at"], str):
                    created_at = datetime.fromisoformat(job["created_at"].replace('Z', '+00:00'))
                else:
                    created_at = job["created_at"]
                
                days_old = (datetime.now() - created_at.replace(tzinfo=None)).days
                if days_old <= 7:
                    score += 1.0
                elif days_old <= 30:
                    score += 0.5
            except:
                pass
        
        return score
    
    def _generate_hybrid_insights(self, db_jobs: List[Dict], scraping_jobs: List[Dict], 
                                 combined_jobs: List[Dict], keywords: List[str], 
                                 scraping_triggered: bool) -> Dict[str, Any]:
        """Generate comprehensive insights from hybrid search results."""
        insights = {
            "search_strategy": "Hybrid database + live scraping",
            "total_results": len(combined_jobs),
            "database_results": len(db_jobs),
            "live_scraping_results": len(scraping_jobs),
            "scraping_triggered": scraping_triggered
        }
        
        if not combined_jobs:
            insights["message"] = "No jobs found matching your criteria across database and live sources."
            return insights
        
        # Analyze job distribution by source type
        source_distribution = {}
        for job in combined_jobs:
            source_type = job.get("source_type", "unknown")
            source_distribution[source_type] = source_distribution.get(source_type, 0) + 1
        
        insights["source_distribution"] = source_distribution
        
        # Analyze top companies across all results
        companies = [job.get('company', 'Unknown') for job in combined_jobs]
        company_counts = {}
        for company in companies:
            company_counts[company] = company_counts.get(company, 0) + 1
        
        insights["top_companies"] = sorted(company_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Analyze locations
        locations = [job.get('location', 'Unknown') for job in combined_jobs if job.get('location')]
        location_counts = {}
        for location in locations:
            location_counts[location] = location_counts.get(location, 0) + 1
        
        insights["top_locations"] = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Analyze relevance scores
        relevance_scores = [job.get("relevance_score", 0) for job in combined_jobs]
        if relevance_scores:
            insights["relevance_analysis"] = {
                "average_score": sum(relevance_scores) / len(relevance_scores),
                "max_score": max(relevance_scores),
                "highly_relevant_jobs": len([s for s in relevance_scores if s >= 5.0])
            }
        
        # Strategy recommendation
        if len(db_jobs) >= 20:
            insights["recommendation"] = "Good database coverage found. Consider database-only searches for faster results."
        elif scraping_triggered and len(scraping_jobs) > 0:
            insights["recommendation"] = "Live scraping provided additional opportunities. Consider hybrid approach for comprehensive coverage."
        else:
            insights["recommendation"] = "Limited results found. Try broader keywords or different locations."
        
        return insights


def hybrid_job_search(keywords: str, location: str = None, max_results: int = 50, 
                     include_scraping: bool = True) -> Dict[str, Any]:
    """
    AutoGen-compatible function for hybrid job search.
    
    Args:
        keywords: Comma-separated keywords to search for
        location: Optional location filter
        max_results: Maximum number of results to return
        include_scraping: Whether to include live scraping
        
    Returns:
        Dictionary with hybrid search results
    """
    tool = HybridSearchTool()
    keyword_list = [k.strip() for k in keywords.split(",")]
    
    request = HybridSearchRequest(
        keywords=keyword_list,
        location=location,
        max_results=max_results,
        include_scraping=include_scraping
    )
    
    return tool.search_jobs_intelligently(request)