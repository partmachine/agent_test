from pydantic import BaseModel
from swarm import Agent

class DevOpsAgent(Agent):
    context_variables: dict = {}
    calling_agent: 'DevOpsAgent' = None