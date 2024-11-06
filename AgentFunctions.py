from tavily import TavilyClient
import os

class AgentFunctions:
    def __init__(self):
        self.tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        self.agent_b = None  # We'll need to set this after initialization
        
    def set_agent_b(self, agent_b):
        """Set the reference to agent_b"""
        self.agent_b = agent_b
        
    def transfer_to_agent_b(self):
        """Transfer control to agent B"""
        if self.agent_b is None:
            raise ValueError("Agent B has not been set")
        return self.agent_b
    
    def web_search(self, query: str):
        """
        Perform a web search using Tavily API
        Args:
            query (str): The search query
        Returns:
            dict: Search results from Tavily
        """
        try:
            search_result = self.tavily.search(query=query)
            return search_result
        except Exception as e:
            return {"error": str(e)}
