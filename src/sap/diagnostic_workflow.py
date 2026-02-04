"""
Veda SAP Diagnostic Agent.
A specialized LangGraph workflow for deep-diving into SAP errors.
It Plans -> Searches -> Analyzes -> Solves.
"""

import os
from typing import TypedDict, Literal, List
import json
import re

from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# Import your existing Search Tool
from ..eyes.search_tool import SearchTool

# --- STATE DEFINITION ---
class SAPState(TypedDict):
    query: str
    category: Literal["performance", "error", "auth", "unknown"]
    severity: Literal["critical", "high", "medium"]
    search_results: str
    diagnosis: str
    final_response: str

# --- THE AGENT CLASS ---
class SAPDiagnosticWorkflow:
    def __init__(self):
        # We use a standard LangChain client for the Agent logic
        self.llm = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model="anthropic/claude-3.5-sonnet", # Use smart model for planning
            temperature=0.2
        )
        self.search_tool = SearchTool()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(SAPState)
        
        # Add Nodes
        workflow.add_node("classify", self._classify_issue)
        workflow.add_node("research", self._research_issue)
        workflow.add_node("diagnose", self._diagnose_issue)
        
        # Add Edges
        workflow.add_edge(START, "classify")
        workflow.add_edge("classify", "research")
        workflow.add_edge("research", "diagnose")
        workflow.add_edge("diagnose", END)
        
        return workflow.compile()

    # --- NODE FUNCTIONS ---

    async def _classify_issue(self, state: SAPState) -> dict:
        """Step 1: Understand what kind of SAP problem this is."""
        prompt = f"""Analyze this SAP issue: "{state['query']}"
        Classify into: performance, error, auth, or unknown.
        Determine severity: critical, high, medium.
        Return JSON."""
        
        msg = [SystemMessage(content="You are a Senior SAP Basis Architect."), HumanMessage(content=prompt)]
        response = await self.llm.ainvoke(msg)
        
        # Simple parsing (fallback to defaults if JSON fails)
        try:
            data = json.loads(response.content)
            return {"category": data.get("category", "unknown"), "severity": data.get("severity", "medium")}
        except:
            return {"category": "unknown", "severity": "medium"}

    async def _research_issue(self, state: SAPState) -> dict:
        """Step 2: Search SAP Help & Community."""
        if state["category"] == "unknown":
            return {"search_results": ""}
            
        # Build targeted query
        q = f"SAP {state['category']} {state['query']} solution"
        
        # Use Veda's eyes
        results = await self.search_tool.search(q, category="sap", max_results=4)
        return {"search_results": results}

    async def _diagnose_issue(self, state: SAPState) -> dict:
        """Step 3: Synthesize a solution."""
        prompt = f"""
        ISSUE: {state['query']}
        CATEGORY: {state['category']}
        CONTEXT: {state['search_results']}
        
        Provide a structured solution:
        1. Root Cause Analysis
        2. T-Codes to check (e.g., SM21, ST22)
        3. Step-by-Step Fix
        """
        
        msg = [SystemMessage(content="You are a Senior SAP Consultant."), HumanMessage(content=prompt)]
        response = await self.llm.ainvoke(msg)
        return {"final_response": response.content}

    # --- ENTRY POINT ---
    async def run(self, query: str) -> str:
        """Run the full diagnostic workflow."""
        initial = {
            "query": query,
            "category": "unknown",
            "severity": "medium",
            "search_results": "",
            "diagnosis": "",
            "final_response": ""
        }
        result = await self.graph.ainvoke(initial)
        return result["final_response"]
