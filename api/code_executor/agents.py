from pydantic_ai import Agent, CodeExecutionTool
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from dotenv import load_dotenv

from .prompts import CODE_EXECUTOR_INSTRUCTIONS
from .models import CodeExecutorOutput

load_dotenv()

model_settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort='low',
    openai_reasoning_summary='detailed'
)

code_execution_agent = Agent(
    'openai-responses:gpt-5',
    builtin_tools=[CodeExecutionTool()],
    instructions=CODE_EXECUTOR_INSTRUCTIONS,
    output_type=CodeExecutorOutput,
    retries=3,
    model_settings=model_settings
)
