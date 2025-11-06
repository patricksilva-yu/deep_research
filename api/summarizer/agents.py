from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from .models import FinalReport
from .prompts import SUMMARIZER_AGENT_INSTRUCTIONS

load_dotenv()

model_settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort='low',
    openai_reasoning_summary='detailed'
)

summarizer_agent = Agent(
    'openai-responses:gpt-5',
    instructions=SUMMARIZER_AGENT_INSTRUCTIONS,
    output_type=FinalReport,
    retries=3,
    model_settings=model_settings
)
