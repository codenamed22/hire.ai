#!/usr/bin/env python3
"""
Hire.AI Agentic CLI - Command line interface for the agentic job search system.

This module provides a comprehensive CLI for interacting with the Hire.AI
agentic system using AutoGen AgentChat patterns.
"""

import sys
import asyncio
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.orchestrator.main import HireAIOrchestrator, JobSearchRequest
from agents.job_search.agent import JobSearchAgent, JobSearchCriteria
from loguru import logger


def setup_application(verbose: bool = False) -> None:
    """
    Setup the application configuration and logging.
    
    Args:
        verbose: Enable verbose logging
    """
    try:
        import os
        from dotenv import load_dotenv
        
        # Load environment variables
        load_dotenv(".env.agents")
        
        # Check for required environment variables
        if not os.getenv("OPENAI_API_KEY"):
            print("❌ Error: OPENAI_API_KEY environment variable not set")
            print("💡 Please create .env.agents file with your OpenAI API key")
            sys.exit(1)
        
        # Configure logging level
        log_level = "DEBUG" if verbose else "INFO"
        logger.remove()  # Remove default handler
        logger.add(sys.stderr, level=log_level)
        
        logger.info("Application setup completed successfully")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)


async def run_orchestrator_search(args: argparse.Namespace) -> None:
    """
    Run a job search using the AutoGen orchestrator.
    
    Args:
        args: Command line arguments
    """
    print("🤖 Initializing Hire.AI AutoGen Orchestrator...")
    
    orchestrator = None
    try:
        orchestrator = HireAIOrchestrator()
        
        print(f"🔍 Searching for: {args.keywords}")
        print(f"📍 Locations: {args.location}")
        print(f"📊 Max Results: {args.max_results}")
        print("\n" + "="*60)
        
        # Execute search using AutoGen agents
        result = await orchestrator.search_jobs(
            keywords=args.keywords,
            location=args.location,
            max_results=args.max_results
        )
        
        print(f"\n✅ {result}")
        
        # Save results if requested
        if args.output:
            # Read the latest export file for saving
            import glob
            import json
            import os
            
            json_files = glob.glob("exports/jobs_export_*.json")
            if json_files:
                latest_file = max(json_files, key=os.path.getctime)
                with open(latest_file, 'r') as f:
                    results = json.load(f)
                save_results({"jobs": results, "success": True}, args.output)
                print(f"\n💾 Results saved to: {args.output}")
            
    except Exception as e:
        logger.error(f"Orchestrator search failed: {e}")
        print(f"❌ Error: {e}")
    finally:
        if orchestrator:
            await orchestrator.close()


def run_agent_search(args: argparse.Namespace) -> None:
    """
    Run a job search using the job search agent directly.
    
    Args:
        args: Command line arguments
    """
    print("🎯 Initializing Job Search Agent...")
    
    try:
        # Create job search agent
        agent = JobSearchAgent()
        
        # Create search criteria
        criteria = JobSearchCriteria(
            keywords=args.keywords,
            location=args.location,
            max_results=args.max_results,
            remote_preference=args.remote,
            experience_level=args.experience
        )
        
        print(f"🔍 Searching for: {args.keywords}")
        print(f"📍 Locations: {args.location}")
        print(f"💼 Experience: {args.experience or 'Any'}")
        print(f"🏠 Remote: {'Preferred' if args.remote else 'No preference'}")
        print("\n" + "="*60)
        
        # Execute search
        results = agent.search_jobs(criteria)
        
        # Display results
        display_agent_results(results)
        
        # Save results if requested
        if args.output:
            save_results(results, args.output)
            print(f"\n💾 Results saved to: {args.output}")
            
    except Exception as e:
        logger.error(f"Agent search failed: {e}")
        print(f"❌ Error: {e}")


async def run_question_mode(args: argparse.Namespace) -> None:
    """
    Run in question mode with the AutoGen orchestrator.
    
    Args:
        args: Command line arguments
    """
    print("💬 Hire.AI AutoGen Question Mode")
    print("Ask me anything about jobs, career advice, or market insights!")
    print("Type 'exit' to quit.\n")
    
    orchestrator = None
    try:
        orchestrator = HireAIOrchestrator()
        
        while True:
            try:
                question = input("❓ Your question: ").strip()
                
                if question.lower() in ['exit', 'quit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                if not question:
                    print("Please enter a question or 'exit' to quit.")
                    continue
                
                print("\n🤔 AutoGen agents are thinking...")
                response = await orchestrator.ask_question(question)
                print(f"\n✅ {response}\n")
                print("-" * 60)
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                logger.error(f"Question processing error: {e}")
                print(f"❌ Error processing question: {e}")
                
    except Exception as e:
        logger.error(f"Question mode failed: {e}")
        print(f"❌ Error: {e}")
    finally:
        if orchestrator:
            await orchestrator.close()


def display_orchestrator_results(results: Dict[str, Any]) -> None:
    """
    Display results from orchestrator search.
    
    Args:
        results: Search results dictionary
    """
    if not results.get("success", False):
        print(f"❌ Search failed: {results.get('error', 'Unknown error')}")
        return
    
    jobs = results.get("jobs", [])
    analysis = results.get("analysis", {})
    recommendations = results.get("recommendations", [])
    conversation = results.get("conversation", [])
    
    print(f"✅ Search completed successfully!")
    print(f"📊 Jobs found: {len(jobs)}")
    
    # Display conversation summary if available
    if conversation:
        print(f"💬 Agent conversation: {len(conversation)} messages")
    
    # Display top jobs
    if jobs:
        print("\n🎯 TOP JOB OPPORTUNITIES:")
        for i, job in enumerate(jobs[:10], 1):
            title = job.get("title", "N/A")
            company = job.get("company", "N/A")
            location = job.get("location", "N/A")
            relevance = job.get("relevance", 0)
            
            print(f"{i:2d}. {title}")
            print(f"    🏢 {company}")
            print(f"    📍 {location}")
            print(f"    ⭐ Relevance: {relevance:.2f}")
            print()
    
    # Display analysis
    if analysis:
        print("🧪 ANALYSIS INSIGHTS:")
        for key, value in analysis.items():
            if isinstance(value, str):
                display_value = value[:200] + ('...' if len(value) > 200 else '')
            else:
                display_value = str(value)[:200] + ('...' if len(str(value)) > 200 else '')
            print(f"📈 {key}: {display_value}")
            print()
    
    # Display recommendations
    if recommendations:
        print("💡 CAREER RECOMMENDATIONS:")
        for i, rec in enumerate(recommendations, 1):
            display_rec = rec[:200] + ('...' if len(str(rec)) > 200 else '')
            print(f"{i}. {display_rec}")
            print()


def display_agent_results(results: Dict[str, Any]) -> None:
    """
    Display results from job search agent.
    
    Args:
        results: Search results dictionary
    """
    if not results.get("success", False):
        print(f"❌ Search failed: {results.get('error', 'Unknown error')}")
        return
    
    jobs = results.get("jobs", [])
    insights = results.get("insights", {})
    
    print(f"✅ Search completed successfully!")
    print(f"📊 Total found: {results.get('total_found', 0)}")
    print(f"🔍 After filtering: {results.get('filtered_count', 0)}")
    print(f"🎯 Final results: {len(jobs)}")
    
    # Display top jobs
    if jobs:
        print("\n🎯 TOP JOB OPPORTUNITIES:")
        for i, job in enumerate(jobs[:15], 1):
            title = job.get("title", "N/A")
            company = job.get("company", "N/A")
            location = job.get("location", "N/A")
            relevance = job.get("relevance", 0)
            rank = job.get("search_rank", i)
            
            print(f"{rank:2d}. {title}")
            print(f"    🏢 {company}")
            print(f"    📍 {location}")
            print(f"    ⭐ Relevance: {relevance:.2f}")
            
            # Show keywords if available
            keywords = job.get("keywords", [])
            if keywords:
                if isinstance(keywords, str):
                    keywords = [k.strip() for k in keywords.split(';')]
                print(f"    🏷️ Skills: {', '.join(keywords[:5])}")
            print()
    
    # Display insights
    if insights:
        print("🧠 SEARCH INSIGHTS:")
        
        if "top_companies" in insights:
            print("🏢 Top Companies:")
            for company, count in list(insights["top_companies"].items())[:5]:
                print(f"   • {company}: {count} jobs")
            print()
        
        if "popular_skills" in insights:
            print("🛠️ Popular Skills:")
            for skill, count in list(insights["popular_skills"].items())[:10]:
                print(f"   • {skill}: {count} mentions")
            print()
        
        if "recommendations" in insights:
            print("💡 Recommendations:")
            for rec in insights["recommendations"]:
                print(f"   • {rec}")
            print()


def save_results(results: Dict[str, Any], output_path: str) -> None:
    """
    Save results to a JSON file.
    
    Args:
        results: Results dictionary
        output_path: Path to save file
    """
    try:
        import json
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Results saved to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save results: {e}")
        print(f"❌ Failed to save results: {e}")


def create_parser() -> argparse.ArgumentParser:
    """
    Create the command line argument parser.
    
    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description="Hire.AI AutoGen Agent Job Search System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run AutoGen orchestrator search
  python agents/cli.py orchestrator "python developer" --location "India,Remote" --max-results 30

  # Run direct agent search  
  python agents/cli.py agent "java spring boot" --location "Bangalore,Mumbai" --remote

  # Interactive question mode
  python agents/cli.py question

  # Search with experience filter
  python agents/cli.py agent "frontend react" --experience senior --output results.json
        """
    )
    
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Enable verbose logging")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Orchestrator command
    orch_parser = subparsers.add_parser("orchestrator", 
                                       help="Run AutoGen orchestrator search")
    orch_parser.add_argument("keywords", 
                            help="Job search keywords (comma-separated)")
    orch_parser.add_argument("--location", "-l", default="India,Remote", 
                            help="Search locations")
    orch_parser.add_argument("--max-results", "-m", type=int, default=50, 
                            help="Maximum results")
    orch_parser.add_argument("--no-analysis", dest="analysis", 
                            action="store_false", help="Disable analysis")
    orch_parser.add_argument("--output", "-o", 
                            help="Output file for results")
    
    # Agent command
    agent_parser = subparsers.add_parser("agent", 
                                        help="Run job search agent directly")
    agent_parser.add_argument("keywords", 
                             help="Job search keywords (comma-separated)")
    agent_parser.add_argument("--location", "-l", default="India,Remote", 
                             help="Search locations")
    agent_parser.add_argument("--max-results", "-m", type=int, default=50, 
                             help="Maximum results")
    agent_parser.add_argument("--experience", "-e", 
                             choices=["junior", "mid", "senior"], 
                             help="Experience level")
    agent_parser.add_argument("--remote", "-r", action="store_true", 
                             help="Prefer remote jobs")
    agent_parser.add_argument("--output", "-o", 
                             help="Output file for results")
    
    # Question command
    question_parser = subparsers.add_parser("question", 
                                           help="Interactive AutoGen question mode")
    
    return parser


async def main_async() -> None:
    """Async main CLI function."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Setup application
    setup_application(args.verbose)
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        # Route to appropriate command
        if args.command == "orchestrator":
            await run_orchestrator_search(args)
        elif args.command == "agent":
            run_agent_search(args)
        elif args.command == "question":
            await run_question_mode(args)
        else:
            parser.print_help()
            
    except KeyboardInterrupt:
        print("\n👋 Operation cancelled by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"❌ Unexpected error: {e}")
        print("   Check logs for more details")


def main() -> None:
    """Main CLI function wrapper."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()