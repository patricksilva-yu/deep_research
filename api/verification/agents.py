from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from dotenv import load_dotenv

from .prompts import VERIFICATION_AGENT_INSTRUCTIONS
from .models import VerificationOutput

load_dotenv()

model_settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort='low',  
    openai_reasoning_summary='detailed'
)

verification_agent = Agent(
    'openai-responses:gpt-5',
    instructions=VERIFICATION_AGENT_INSTRUCTIONS,
    output_type=VerificationOutput,
    retries=3,
    model_settings=model_settings
)
