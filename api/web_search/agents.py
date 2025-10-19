from pydantic_ai import Agent
from pydantic_ai.common_tools.tavily import tavily_search_tool
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
import os
from .prompts import WEB_SEARCH_AGENT_INSTRUCTIONS
from .models import SearchAgentOutput
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("TAVILY_API_KEY")

model_settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort='medium',
    openai_reasoning_summary='detailed'
)

web_search_agent = Agent(
    'openai-responses:gpt-5',
    tools=[tavily_search_tool(api_key)],
    instructions=WEB_SEARCH_AGENT_INSTRUCTIONS,
    output_type=SearchAgentOutput,
    retries=3,
    model_settings=model_settings
)
