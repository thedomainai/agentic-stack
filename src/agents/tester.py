"""
Tester Agent - Handles testing and validation tasks.

This agent specializes in test generation, test execution,
coverage analysis, and quality validation.
"""

import asyncio
from typing import Any

import anthropic

from ..config import get_settings
from ..core.agent_base import BaseAgent, TaskResult
from ..services.rabbitmq_client import TaskMessage


class TesterAgent(BaseAgent):
    """
    Agent specialized in testing and validation.

    Capabilities:
    - Test case generation
    - Test execution
    - Coverage analysis
    - Bug reproduction
    - Regression testing
    """

    AGENT_TYPE = "tester"
    CAPABILITIES = [
        "task.assign",
        "test.generate",
        "test.execute",
        "test.coverage",
        "test.validate",
        "bug.reproduce",
    ]

    def __init__(self, **kwargs):
        """Initialize the Tester agent."""
        super().__init__(**kwargs)
        self._settings = get_settings()
        self._anthropic: anthropic.AsyncAnthropic | None = None

    async def start(self) -> None:
        """Start the agent and initialize LLM client."""
        await super().start()

        api_key = self._settings.llm.api_key
        if api_key:
            self._anthropic = anthropic.AsyncAnthropic(api_key=api_key)
            self.logger.info("Anthropic client initialized")
        else:
            self.logger.warning("No API key configured - LLM calls will fail")

    async def execute_task(self, message: TaskMessage) -> TaskResult:
        """
        Execute a testing task.

        Args:
            message: Task message with action and payload

        Returns:
            TaskResult with test results or error
        """
        action = message.action
        payload = message.payload

        self.logger.info(f"Executing action: {action}")

        if action == "task.assign":
            return await self._handle_generic_task(payload)
        elif action == "test.generate":
            return await self._generate_tests(payload)
        elif action == "test.execute":
            return await self._execute_tests(payload)
        elif action == "test.coverage":
            return await self._analyze_coverage(payload)
        elif action == "test.validate":
            return await self._validate_functionality(payload)
        elif action == "bug.reproduce":
            return await self._reproduce_bug(payload)
        else:
            return TaskResult(
                success=False,
                error=f"Unknown action: {action}",
            )

    async def _handle_generic_task(self, payload: dict[str, Any]) -> TaskResult:
        """Handle a generic testing task."""
        title = payload.get("title", "")
        description = payload.get("description", "")

        prompt = f"""You are a QA engineer. Analyze the following testing task
and provide a comprehensive testing approach.

Task: {title}

Description: {description}

Provide your response in the following format:
1. Test Scope: What needs to be tested
2. Test Strategy: Approach for testing
3. Test Cases: High-level test cases to create
4. Test Data: Data requirements for testing
5. Risks: Testing risks and mitigation"""

        response = await self._call_llm(prompt)

        if response:
            return TaskResult(
                success=True,
                result={
                    "response": response,
                    "task_title": title,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to generate response from LLM",
            )

    async def _generate_tests(self, payload: dict[str, Any]) -> TaskResult:
        """Generate test cases for code."""
        code = payload.get("code", "")
        language = payload.get("language", "python")
        test_framework = payload.get("framework", "pytest")
        coverage_target = payload.get("coverage_target", "high")

        prompt = f"""Generate comprehensive test cases for the following {language} code.

Code:
```{language}
{code}
```

Test Framework: {test_framework}
Coverage Target: {coverage_target}

Requirements:
- Write thorough unit tests
- Cover edge cases and error conditions
- Use proper test organization
- Include setup/teardown if needed
- Add descriptive test names
- Mock external dependencies appropriately

Generate complete, runnable test code."""

        response = await self._call_llm(prompt)

        if response:
            await self._log_discovery(
                category="test_generation",
                title=f"Generated {test_framework} tests",
                description=f"Created tests with {coverage_target} coverage target",
                confidence=0.8,
                tags=[language, test_framework, "generated"],
            )

            return TaskResult(
                success=True,
                result={
                    "tests": response,
                    "language": language,
                    "framework": test_framework,
                },
                artifacts=[{
                    "name": "generated_tests",
                    "type": "code",
                    "language": language,
                    "framework": test_framework,
                }],
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to generate tests",
            )

    async def _execute_tests(self, payload: dict[str, Any]) -> TaskResult:
        """Execute tests and report results."""
        test_command = payload.get("command", "pytest")
        test_path = payload.get("path", "tests/")
        timeout = payload.get("timeout", 300)

        try:
            # Execute the test command
            process = await asyncio.create_subprocess_shell(
                f"{test_command} {test_path} --tb=short -v",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return TaskResult(
                    success=False,
                    error=f"Test execution timed out after {timeout}s",
                )

            output = stdout.decode() if stdout else ""
            error_output = stderr.decode() if stderr else ""

            success = process.returncode == 0

            return TaskResult(
                success=success,
                result={
                    "output": output,
                    "errors": error_output,
                    "return_code": process.returncode,
                    "command": f"{test_command} {test_path}",
                },
            )

        except Exception as e:
            return TaskResult(
                success=False,
                error=f"Failed to execute tests: {str(e)}",
            )

    async def _analyze_coverage(self, payload: dict[str, Any]) -> TaskResult:
        """Analyze test coverage."""
        code = payload.get("code", "")
        tests = payload.get("tests", "")
        language = payload.get("language", "python")

        prompt = f"""Analyze the test coverage for the following code and tests.

Source Code:
```{language}
{code}
```

Test Code:
```{language}
{tests}
```

Provide:
1. Coverage Analysis: What is covered and what isn't
2. Branch Coverage: Analysis of branch/conditional coverage
3. Edge Cases: Missing edge case tests
4. Critical Paths: Important code paths that need testing
5. Recommendations: Specific tests to add for better coverage
6. Estimated Coverage: Rough percentage estimate"""

        response = await self._call_llm(prompt)

        if response:
            return TaskResult(
                success=True,
                result={
                    "coverage_analysis": response,
                    "language": language,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to analyze coverage",
            )

    async def _validate_functionality(self, payload: dict[str, Any]) -> TaskResult:
        """Validate that functionality works as expected."""
        specification = payload.get("specification", "")
        implementation = payload.get("implementation", "")
        test_scenarios = payload.get("scenarios", [])

        scenarios_text = "\n".join(f"- {s}" for s in test_scenarios) if test_scenarios else "Standard scenarios"

        prompt = f"""Validate that the implementation meets the specification.

Specification:
{specification}

Implementation:
{implementation}

Test Scenarios:
{scenarios_text}

Provide:
1. Specification Compliance: Does the implementation meet requirements?
2. Functionality Check: Does each feature work correctly?
3. Boundary Conditions: Are edge cases handled?
4. Error Handling: Are errors handled appropriately?
5. Issues Found: Any problems identified
6. Validation Result: PASS/FAIL with explanation"""

        response = await self._call_llm(prompt)

        if response:
            # Determine if validation passed
            passed = "pass" in response.lower() and "fail" not in response.lower()

            await self._log_decision(
                decision_type="validation_result",
                context="Functionality validation",
                options_considered=[
                    {"option": "pass", "rationale": "Implementation meets specification"},
                    {"option": "fail", "rationale": "Implementation has issues"},
                ],
                chosen_option="pass" if passed else "fail",
                rationale="Based on specification compliance analysis",
            )

            return TaskResult(
                success=True,
                result={
                    "validation": response,
                    "passed": passed,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to validate functionality",
            )

    async def _reproduce_bug(self, payload: dict[str, Any]) -> TaskResult:
        """Attempt to reproduce a reported bug."""
        bug_description = payload.get("description", "")
        code = payload.get("code", "")
        steps = payload.get("steps", [])
        expected = payload.get("expected", "")
        actual = payload.get("actual", "")

        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) if steps else "No steps provided"

        prompt = f"""Analyze and provide reproduction steps for the following bug.

Bug Description: {bug_description}

Code:
{code}

Steps to Reproduce:
{steps_text}

Expected Behavior: {expected}
Actual Behavior: {actual}

Provide:
1. Root Cause Analysis: Likely cause of the bug
2. Reproduction Steps: Detailed steps to reproduce
3. Minimal Test Case: Smallest code to reproduce the bug
4. Fix Suggestion: How to fix the bug
5. Regression Test: Test to prevent recurrence"""

        response = await self._call_llm(prompt)

        if response:
            await self._log_discovery(
                category="bug_analysis",
                title=f"Bug analysis: {bug_description[:50]}",
                description="Analyzed bug and provided reproduction steps",
                confidence=0.7,
                tags=["bug", "reproduction"],
            )

            return TaskResult(
                success=True,
                result={
                    "analysis": response,
                    "bug_description": bug_description,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to analyze bug",
            )

    async def _call_llm(self, prompt: str) -> str | None:
        """Call the LLM API with a prompt."""
        if not self._anthropic:
            self.logger.error("Anthropic client not initialized")
            return None

        try:
            response = await self._anthropic.messages.create(
                model=self._settings.llm.model,
                max_tokens=self._settings.llm.max_tokens,
                temperature=self._settings.llm.temperature,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )

            if response.content:
                return response.content[0].text

            return None

        except anthropic.APIError as e:
            self.logger.error(f"LLM API error: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Unexpected error calling LLM: {e}")
            return None
