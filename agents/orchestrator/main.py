"""
Hire.AI Orchestrator Agent
Modern implementation using AutoGen AgentChat following official patterns.
Properly integrates job scraping tools with conversational agents.
"""

import os
import json
import asyncio
import subprocess
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient

from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv(".env.agents")

# Scraper tool function for AutoGen agents
async def scrape_jobs(keywords: str, location: str = "India,Remote", max_results: int = 50) -> str:
    """
    Job scraping tool that AutoGen agents can use.
    Calls the Go scraper and returns formatted results.
    """
    try:
        logger.info(f"Starting job scrape: {keywords} in {location}")
        
        # Run the Go scraper
        cmd = ["./bin/job-scraper"]
        env = os.environ.copy()
        env.update({
            "KEYWORDS": keywords,
            "LOCATION": location,
            "MAX_RESULTS": str(max_results)
        })
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode != 0:
            error_msg = f"Scraper failed: {result.stderr}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        
        # Try to read the results from exports directory
        import glob
        import pandas as pd
        
        # Find the latest export file
        json_files = glob.glob("exports/jobs_export_*.json")
        if not json_files:
            return "Error: No job data found after scraping"
        
        latest_file = max(json_files, key=os.path.getctime)
        
        with open(latest_file, 'r') as f:
            jobs_data = json.load(f)
        
        if not jobs_data:
            return "No jobs found matching your criteria."
        
        # Format results for the agent
        job_count = len(jobs_data)
        
        # Get summary statistics
        companies = {}
        locations = {}
        keywords_found = {}
        
        for job in jobs_data[:20]:  # Limit to first 20 for summary
            company = job.get('company', 'Unknown')
            companies[company] = companies.get(company, 0) + 1
            
            loc = job.get('location', 'Unknown')
            locations[loc] = locations.get(loc, 0) + 1
            
            job_keywords = job.get('keywords', [])
            if job_keywords:
                for kw in job_keywords:
                    keywords_found[kw] = keywords_found.get(kw, 0) + 1
        
        # Create summary response
        top_companies = sorted(companies.items(), key=lambda x: x[1], reverse=True)[:5]
        top_locations = sorted(locations.items(), key=lambda x: x[1], reverse=True)[:5]
        top_keywords = sorted(keywords_found.items(), key=lambda x: x[1], reverse=True)[:5]
        
        summary = f"""
Job Search Results for "{keywords}" in {location}:

📊 SUMMARY:
- Total jobs found: {job_count}
- Search completed successfully

🏢 TOP COMPANIES:
{chr(10).join([f"- {company}: {count} jobs" for company, count in top_companies])}

📍 TOP LOCATIONS:
{chr(10).join([f"- {location}: {count} jobs" for location, count in top_locations])}

🔧 TOP SKILLS/KEYWORDS:
{chr(10).join([f"- {keyword}: {count} mentions" for keyword, count in top_keywords])}

📄 SAMPLE JOBS:
{chr(10).join([f"- {job.get('title', 'Unknown')} at {job.get('company', 'Unknown')} ({job.get('location', 'Unknown')})" for job in jobs_data[:5]])}

💾 Full results saved to: {latest_file}
"""
        
        logger.info(f"Job scrape completed: {job_count} jobs found")
        return summary
        
    except subprocess.TimeoutExpired:
        error_msg = "Job scraping timed out after 5 minutes"
        logger.error(error_msg)
        return f"Error: {error_msg}"
    except Exception as e:
        error_msg = f"Job scraping failed: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"


async def analyze_job_market(keywords: str, location: str = "India,Remote") -> str:
    """
    Job market analysis tool for AutoGen agents.
    Provides market insights and trends.
    """
    try:
        # This would integrate with your analysis logic
        # For now, providing a template response
        analysis = f"""
Job Market Analysis for "{keywords}" in {location}:

📈 MARKET TRENDS:
- High demand for {keywords} skills in the current market
- Growing remote work opportunities
- Competitive salary ranges vary by experience level

💡 INSIGHTS:
- Companies are actively hiring for these skills
- Consider highlighting relevant experience
- Remote positions offer flexibility and wider opportunities

📋 RECOMMENDATIONS:
- Keep skills updated with latest technologies
- Build a strong portfolio showcasing relevant projects
- Network with professionals in your target companies
"""
        return analysis
        
    except Exception as e:
        return f"Error analyzing job market: {str(e)}"


@dataclass
class JobSearchRequest:
    """Structure for job search requests."""
    keywords: str
    location: str = "India,Remote"
    max_results: int = 50
    analysis_required: bool = True


class HireAIOrchestrator:
    """
    Modern AutoGen-based orchestrator following official patterns.
    Integrates job scraping tools directly with conversational agents.
    """
    
    def __init__(self):
        """Initialize the orchestrator with all required agents and tools."""
        
        # Setup OpenAI model client
        self.model_client = OpenAIChatCompletionClient(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Initialize agents with tools
        self._setup_agents()
        
        logger.info("HireAI Orchestrator initialized with AutoGen AgentChat")

    def _setup_agents(self):
        """Set up AutoGen agents following official patterns."""
        
        # Job Search Agent with scraping tools
        self.job_search_agent = AssistantAgent(
            name="job_search_agent",
            model_client=self.model_client,
            tools=[scrape_jobs],  # Direct tool integration
            system_message="""You are a Job Search Specialist. Your role is to help users find relevant job opportunities.

Key capabilities:
- Use the scrape_jobs tool to search for positions
- Provide summaries of job search results
- Identify top companies and trending skills
- Offer practical job search insights

When a user asks for jobs:
1. Use scrape_jobs with their keywords and location preferences
2. Analyze the results and provide clear summaries
3. Highlight the most relevant opportunities
4. Give practical next steps

Always be helpful and focus on actionable results.""",
            reflect_on_tool_use=True  # Enable reflection on tool usage
        )
        
        # Market Analysis Agent
        self.market_analyst = AssistantAgent(
            name="market_analyst",
            model_client=self.model_client,
            tools=[analyze_job_market],  # Market analysis tool
            system_message="""You are a Job Market Analyst. You provide insights into employment trends and market conditions.

Your expertise includes:
- Analyzing job market trends and patterns
- Identifying high-demand skills and technologies
- Providing salary and compensation insights
- Offering strategic career advice based on market data

Use the analyze_job_market tool to provide data-driven insights about:
- Market demand for specific skills
- Salary trends and ranges
- Growth opportunities in different sectors
- Strategic career recommendations

Always provide actionable market intelligence.""",
            reflect_on_tool_use=True
        )
        
        # Career Advisor Agent (conversational only)
        self.career_advisor = AssistantAgent(
            name="career_advisor",
            model_client=self.model_client,
            system_message="""You are a Career Development Advisor. You help users make strategic career decisions.

Your role includes:
- Providing personalized career guidance
- Suggesting skill development strategies
- Offering job application and interview advice
- Helping align opportunities with career goals

Focus on:
- Understanding user career aspirations
- Recommending learning and development paths
- Providing practical application strategies
- Supporting long-term career planning

Be encouraging, practical, and focused on actionable advice."""
        )
        
        # Setup termination condition
        self.termination = TextMentionTermination("TERMINATE")
        
        # Create team with simplified agent set
        self.team = RoundRobinGroupChat(
            [self.job_search_agent, self.market_analyst, self.career_advisor],
            termination_condition=self.termination
        )

    async def search_jobs(self, keywords: str, location: str = "India,Remote", max_results: int = 50) -> str:
        """
        Search for jobs using the agent team (simplified AutoGen pattern).
        
        Args:
            keywords: Job search keywords
            location: Search location
            max_results: Maximum number of results
            
        Returns:
            String response from the agent team
        """
        try:
            prompt = f"""
Please help me find job opportunities for:
- Keywords: {keywords}
- Location: {location}
- Max results: {max_results}

Use your tools to search for jobs and provide insights. When finished, say TERMINATE.
"""
            
            logger.info(f"Starting job search: {keywords} in {location}")
            
            # Run the agent team
            result = await self.team.run(task=prompt)
            
            # Stream the conversation to console
            for message in result.messages:
                print(f"\n[{message.source}]: {message.content}")
            
            return "Job search completed - see conversation above for results"
            
        except Exception as e:
            logger.error(f"Job search failed: {str(e)}")
            return f"Error: {str(e)}"

    async def ask_question(self, question: str) -> str:
        """
        Ask a general question to the agent team.
        
        Args:
            question: User's question
            
        Returns:
            String response from the team
        """
        try:
            prompt = f"{question}\n\nWhen finished with your response, say TERMINATE."
            
            logger.info(f"Processing question: {question[:50]}...")
            
            result = await self.team.run(task=prompt)
            
            # Stream conversation to console
            for message in result.messages:
                print(f"\n[{message.source}]: {message.content}")
            
            return "Question answered - see conversation above"
                
        except Exception as e:
            logger.error(f"Question processing failed: {str(e)}")
            return f"Error: {str(e)}"

    async def close(self):
        """Close the model client connections."""
        try:
            await self.model_client.close()
            logger.info("Model client connections closed")
        except Exception as e:
            logger.error(f"Error closing connections: {str(e)}")


# Main function for testing
async def main():
    """Main function demonstrating AutoGen usage."""
    orchestrator = HireAIOrchestrator()
    
    try:
        print("🤖 HireAI AutoGen Agent System")
        print("=" * 50)
        
        # Example job search
        print("\n🔍 Searching for Python jobs...")
        await orchestrator.search_jobs("python developer", "India", 20)
        
        print("\n" + "=" * 50)
        print("✅ Example completed!")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    finally:
        await orchestrator.close()


if __name__ == "__main__":
    # Ensure we have the required environment
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Please create .env.agents file with your OpenAI API key")
        exit(1)
    
    # Run the example
    asyncio.run(main())