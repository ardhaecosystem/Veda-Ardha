"""
Veda's Eyes - Web search using SearXNG.
Optimized for SAP-specific queries with token-efficient formatting.
"""

import aiohttp
import os
from typing import List, Dict, Literal
import structlog

logger = structlog.get_logger()


class SearchTool:
    """
    Interface to SearXNG for external knowledge retrieval.
    Configured for SAP and automation-specific searches.
    """
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.getenv("SEARXNG_HOST", "http://localhost:8888")
    
    async def search(
        self,
        query: str,
        category: Literal["general", "sap", "it", "tech"] = "general",
        max_results: int = 5,
    ) -> str:
        """
        Search the web and return formatted results.
        
        Args:
            query: Search query
            category: Search category for optimization
                - "sap": SAP-specific sources
                - "it": StackOverflow, technical forums
                - "tech": General tech sites
                - "general": All sources
            max_results: Maximum number of results to return
            
        Returns:
            Formatted search results as markdown
        """
        
        # Map category to SearXNG categories
        category_map = {
            "sap": "it",
            "it": "it",
            "tech": "science,it",
            "general": "general",
        }
        
        params = {
            "q": query,
            "format": "json",
            "categories": category_map.get(category, "general"),
            "language": "en",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        logger.error("search_failed", status=resp.status)
                        return "Error: Could not access search engine."
                    
                    data = await resp.json()
                    results = data.get("results", [])[:max_results]
                    
                    if not results:
                        return "No results found."
                    
                    # Format results for LLM consumption (token-efficient)
                    formatted = "## Search Results\n\n"
                    for i, r in enumerate(results, 1):
                        title = r.get("title", "Untitled")
                        url = r.get("url", "")
                        content = r.get("content", "")[:200]  # Limit to 200 chars
                        
                        formatted += f"{i}. **{title}**\n"
                        formatted += f"   {content}...\n"
                        formatted += f"   Source: {url}\n\n"
                    
                    logger.info("search_completed", results_count=len(results))
                    return formatted
                    
        except Exception as e:
            logger.error("search_exception", error=str(e))
            return f"Search error: {str(e)}"
    
    async def deep_research(
        self,
        query: str,
        num_queries: int = 3,
    ) -> Dict:
        """
        Perform deep research by running multiple related searches.
        Used for complex SAP issues requiring comprehensive investigation.
        
        Returns dict with:
            - summary: Executive summary
            - findings: Detailed findings
            - sources: List of sources
        """
        
        logger.info("deep_research_started", query=query)
        
        # This would use the research model (Kimi K2.5) to:
        # 1. Generate related search queries
        # 2. Search for each
        # 3. Synthesize findings
        # 4. Generate markdown report
        
        # For now, simplified implementation
        results = await self.search(query, category="sap", max_results=10)
        
        return {
            "summary": "Deep research placeholder",
            "findings": results,
            "sources": [],
        }
