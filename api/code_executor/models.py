from pydantic import BaseModel, Field
from typing import Optional, List


class CodeExecutionResult(BaseModel):
    """Individual code execution result."""
    code: str = Field(
        description="The Python code that was executed"
    )
    output: Optional[str] = Field(
        default=None,
        description="Standard output from the code execution"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if execution failed"
    )
    execution_time: Optional[float] = Field(
        default=None,
        description="Execution time in seconds"
    )


class CodeExecutorOutput(BaseModel):
    """Output from the code executor agent."""
    summary: str = Field(
        description="Brief explanation of what was accomplished"
    )
    executions: List[CodeExecutionResult] = Field(
        description="List of code executions performed"
    )
    next_steps: Optional[List[str]] = Field(
        default=None,
        description="Suggested next steps or follow-up actions"
    )
