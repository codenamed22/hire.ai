"""
Database search tool for querying jobs from PostgreSQL database.

This tool provides intelligent search capabilities over stored job data,
with support for keyword matching, location filtering, and relevance scoring.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from dataclasses import dataclass
from agents.core.dependency_injection import injectable


@dataclass
class DatabaseSearchQuery:
    keywords: List[str]
    location: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    experience_level: Optional[str] = None
    is_remote: Optional[bool] = None
    limit: int = 50
    offset: int = 0


@injectable
class DatabaseSearchTool:
    """Tool for searching jobs in the PostgreSQL database."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.connection_params = {
            'host': 'localhost',
            'port': 5432,
            'database': 'hire_ai',
            'user': 'postgres',
            'password': 'postgres'
        }
    
    def get_connection(self):
        """Get database connection."""
        try:
            return psycopg2.connect(**self.connection_params)
        except psycopg2.Error as e:
            self.logger.error(f"Database connection failed: {e}")
            raise
    
    def intelligent_search(self, keywords: List[str], location: Optional[str] = None, 
                          max_results: int = 25) -> Dict[str, Any]:
        """
        Perform intelligent job search with keyword and location filtering.
        
        Args:
            keywords: List of keywords to search for
            location: Optional location filter
            max_results: Maximum number of results to return
            
        Returns:
            Dictionary with search results and metadata
        """
        try:
            query = DatabaseSearchQuery(
                keywords=keywords,
                location=location,
                limit=max_results,
                offset=0
            )
            
            jobs = self.search_jobs(query)
            
            # Calculate insights
            insights = self._generate_search_insights(jobs, keywords)
            
            return {
                "success": True,
                "jobs": jobs,
                "total_found": len(jobs),
                "insights": insights,
                "search_terms": keywords,
                "location_filter": location
            }
            
        except Exception as e:
            self.logger.error(f"Database search failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "jobs": [],
                "total_found": 0
            }
    
    def search_jobs(self, query: DatabaseSearchQuery) -> List[Dict[str, Any]]:
        """
        Search jobs based on the provided query parameters.
        
        Args:
            query: DatabaseSearchQuery object with search parameters
            
        Returns:
            List of job dictionaries
        """
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Build the SQL query
                sql_query = """
                    SELECT 
                        id, title, company, location, salary, description, 
                        link, source, keywords, experience_level, is_remote,
                        created_at, relevance_score
                    FROM jobs 
                    WHERE 1=1
                """
                params = []
                
                # Add keyword filtering using full-text search
                if query.keywords:
                    keyword_conditions = []
                    for i, keyword in enumerate(query.keywords):
                        keyword_conditions.append(f"(title ILIKE ${len(params)+1} OR description ILIKE ${len(params)+1} OR keywords ILIKE ${len(params)+1})")
                        params.append(f"%{keyword}%")
                    
                    sql_query += f" AND ({' OR '.join(keyword_conditions)})"
                
                # Add location filtering
                if query.location:
                    sql_query += f" AND location ILIKE ${len(params)+1}"
                    params.append(f"%{query.location}%")
                
                # Add date filtering
                if query.date_from:
                    sql_query += f" AND created_at >= ${len(params)+1}"
                    params.append(query.date_from)
                
                if query.date_to:
                    sql_query += f" AND created_at <= ${len(params)+1}"
                    params.append(query.date_to)
                
                # Add experience level filtering
                if query.experience_level:
                    sql_query += f" AND experience_level = ${len(params)+1}"
                    params.append(query.experience_level)
                
                # Add remote filtering
                if query.is_remote is not None:
                    sql_query += f" AND is_remote = ${len(params)+1}"
                    params.append(query.is_remote)
                
                # Add ordering and pagination
                sql_query += " ORDER BY created_at DESC, relevance_score DESC"
                sql_query += f" LIMIT ${len(params)+1} OFFSET ${len(params)+2}"
                params.extend([query.limit, query.offset])
                
                # Execute query
                cursor.execute(sql_query, params)
                rows = cursor.fetchall()
                
                # Convert to list of dictionaries
                jobs = []
                for row in rows:
                    job_dict = dict(row)
                    # Convert datetime to string for JSON serialization
                    if job_dict.get('created_at'):
                        job_dict['created_at'] = job_dict['created_at'].isoformat()
                    jobs.append(job_dict)
                
                return jobs
    
    def get_job_statistics(self) -> Dict[str, Any]:
        """Get statistics about jobs in the database."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Total jobs
                cursor.execute("SELECT COUNT(*) as total_jobs FROM jobs")
                total_jobs = cursor.fetchone()['total_jobs']
                
                # Jobs by source
                cursor.execute("""
                    SELECT source, COUNT(*) as count 
                    FROM jobs 
                    GROUP BY source 
                    ORDER BY count DESC
                """)
                jobs_by_source = dict(cursor.fetchall())
                
                # Jobs by location
                cursor.execute("""
                    SELECT location, COUNT(*) as count 
                    FROM jobs 
                    WHERE location IS NOT NULL 
                    GROUP BY location 
                    ORDER BY count DESC 
                    LIMIT 10
                """)
                top_locations = dict(cursor.fetchall())
                
                # Recent activity
                cursor.execute("""
                    SELECT DATE(created_at) as date, COUNT(*) as count 
                    FROM jobs 
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                    GROUP BY DATE(created_at) 
                    ORDER BY date DESC
                """)
                recent_activity = dict(cursor.fetchall())
                
                return {
                    "total_jobs": total_jobs,
                    "jobs_by_source": jobs_by_source,
                    "top_locations": top_locations,
                    "recent_activity": recent_activity
                }
    
    def _generate_search_insights(self, jobs: List[Dict[str, Any]], keywords: List[str]) -> Dict[str, Any]:
        """Generate insights from search results."""
        if not jobs:
            return {"message": "No jobs found matching your criteria."}
        
        # Analyze companies
        companies = [job.get('company', 'Unknown') for job in jobs]
        company_counts = {}
        for company in companies:
            company_counts[company] = company_counts.get(company, 0) + 1
        
        # Analyze locations
        locations = [job.get('location', 'Unknown') for job in jobs if job.get('location')]
        location_counts = {}
        for location in locations:
            location_counts[location] = location_counts.get(location, 0) + 1
        
        # Analyze sources
        sources = [job.get('source', 'Unknown') for job in jobs]
        source_counts = {}
        for source in sources:
            source_counts[source] = source_counts.get(source, 0) + 1
        
        return {
            "total_results": len(jobs),
            "top_companies": sorted(company_counts.items(), key=lambda x: x[1], reverse=True)[:5],
            "top_locations": sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[:5],
            "sources": source_counts,
            "keywords_used": keywords
        }


def search_database_jobs(keywords: str, location: str = None, max_results: int = 25) -> Dict[str, Any]:
    """
    AutoGen-compatible function for database job search.
    
    Args:
        keywords: Comma-separated keywords to search for
        location: Optional location filter
        max_results: Maximum number of results to return
        
    Returns:
        Dictionary with search results
    """
    tool = DatabaseSearchTool()
    keyword_list = [k.strip() for k in keywords.split(",")]
    return tool.intelligent_search(keyword_list, location, max_results)