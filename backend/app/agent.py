import json
import time
from dataclasses import dataclass, field

import openai

from app.config import LLM_MODEL
from app.db import get_connection
from app.llm import get_client
from app.tools import TOOL_SCHEMAS, run_tool

MAX_STEPS = 8                  # most tool-calling rounds before we force an answer
KEEP_FULL_RESULTS = 3          # the newest tool results stay complete
OLD_RESULT_CHARS = 300         # older tool results are cut down to this many characters
FINAL_EVIDENCE_CHARS = 12000   # evidence budget for the forced final answer
RATE_LIMIT_WAITS = [15, 30, 60]  # seconds to wait before each retry

SYSTEM_PROMPT = """You are RepoPilot, an assistant that explains a codebase to a developer who has never seen it. The repository is {repo}.

You can only see the repository through your tools. Work like this:
1. Use search_code to find the relevant code. If the results look off, rephrase and search again.
2. Use read_symbol to read a whole function or class by name. Use read_file only for other line ranges, such as imports at the top of a file.
3. Use get_callers and get_callees for questions about flow or usage ("who uses X", "what happens when X runs").
4. Never repeat a tool call you have already made: its result is already in the conversation. If a result says it was cut off, continue from the line it names with read_file.
5. Stop using tools as soon as you have enough evidence. Three to five tool calls are usually enough.

Rules:
- Base every statement on code you have actually seen in tool results. Never invent functions, files or behaviour.
- Cite your evidence as path:start-end (for example src/pkg/core.py:40-72) next to each claim.
- Say so when a claim rests only on a docstring or comment and not on code you read.
- If you cannot find the answer, say what you searched for and what you found instead.
- The call graph is static analysis and can miss calls made through objects of unknown type. Say so when it matters.
- Keep answers short and concrete: the direct answer first, then the key steps."""

# Used only for the forced final answer. It must not mention tools at all.
FINAL_SYSTEM_PROMPT = """You are RepoPilot, an assistant that explains the codebase {repo} to a developer. You are given a question and notes copied from the repository's source code. Write your answer in plain text. You cannot look anything else up.

Rules:
- Base every statement on the notes. Never invent functions, files or behaviour.
- Cite your evidence as path:start-end next to each claim.
- Say so when a claim rests only on a docstring, or when the notes do not cover something.
- Keep the answer short: the direct answer first, then the key steps."""

FAILED_RESULT_PREFIXES = ("Bad arguments", "You already made", "Unknown tool", "The tool ")


def to_openai_tools(schemas):
    """Our tool descriptions, in the format OpenAI-compatible providers expect."""
    return [
        {
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s["description"],
                "parameters": s["input_schema"],
            },
        }
        for s in schemas
    ]


OPENAI_TOOLS = to_openai_tools(TOOL_SCHEMAS)


@dataclass
class ToolStep:
    name: str
    arguments: dict
    result: str


@dataclass
class AgentResult:
    answer: str
    steps: list[ToolStep] = field(default_factory=list)
    tokens: int = 0
    hit_step_limit: bool = False  

def _repo_name(repo_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT name FROM repositories WHERE id = %s", (repo_id,)).fetchone()
    if row is None:
        raise ValueError(f"No repository with id {repo_id}")
    return row[0]


def _trim_old_results(messages: list[dict]) -> None:
    """Shrink old tool results so the conversation does not grow without limit."""
    positions = [i for i, m in enumerate(messages) if m["role"] == "tool"]
    for i in positions[:-KEEP_FULL_RESULTS]:
        content = messages[i]["content"]
        if len(content) > OLD_RESULT_CHARS:
            messages[i]["content"] = content[:OLD_RESULT_CHARS] + "\n...[older result trimmed]"


def _chat(client, messages: list[dict], use_tools: bool = True):
    """One model call, retried with waits if the provider says we are going too fast."""
    for wait in [0] + RATE_LIMIT_WAITS:
        if wait:
            print(f"  (rate limited, waiting {wait}s...)")
            time.sleep(wait)
        try:
            kwargs = {"model": LLM_MODEL, "messages": messages}
            if use_tools:
                kwargs["tools"] = OPENAI_TOOLS
            return client.chat.completions.create(**kwargs)
        except openai.RateLimitError:
            continue
    raise RuntimeError("Still rate limited after several retries. Wait a few minutes and try again.")

def _final_answer(client, repo_name: str, question: str, steps: list[ToolStep]):
    """Force an answer from the evidence gathered so far.

    The request mentions no tools anywhere: no tool names, no tool-call history.
    When it did, the model tried to call a tool even though none were offered.
    """
    pieces = []
    budget = FINAL_EVIDENCE_CHARS
    for step in reversed(steps):  # newest evidence first
        if step.result.startswith(FAILED_RESULT_PREFIXES):
            continue  # a failed call carries no evidence
        block = step.result[:2500]
        if len(block) + 30 > budget:
            break
        pieces.append(block)
        budget -= len(block) + 30
    evidence = "\n\n--- next source ---\n\n".join(reversed(pieces)) or "(nothing relevant was found)"

    user_text = (
        f"Question: {question}\n\n"
        f"Notes copied from the repository:\n\n{evidence}\n\n"
        "Answer the question in plain text using only these notes. "
        "Cite as path:start-end. Say clearly what is uncertain or was not verified."
    )
    attempts = [
        user_text,
        user_text + "\n\nReply with plain text only. Do not call any function.",
    ]
    for text in attempts:
        messages = [
            {"role": "system", "content": FINAL_SYSTEM_PROMPT.format(repo=repo_name)},
            {"role": "user", "content": text},
        ]
        try:
            response = _chat(client, messages, use_tools=False)
        except openai.BadRequestError:
            continue
        used = response.usage.total_tokens if response.usage else 0
        return response.choices[0].message.content or "", used

    return "The evidence was gathered, but the model could not write the final answer. Try again.", 0


def ask(repo_id: int, question: str, max_steps: int = MAX_STEPS, on_step=None) -> AgentResult:
    """Answer a question about a repository, using tools to look at its code."""
    client = get_client()
    repo_name = _repo_name(repo_id)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(repo=repo_name)},
        {"role": "user", "content": question},
    ]
    steps: list[ToolStep] = []
    seen_calls: set = set()
    tokens = 0

    for _ in range(max_steps):
        _trim_old_results(messages)
        try:
            response = _chat(client, messages)
        except openai.BadRequestError as error:
            if "tool" in str(error).lower():
                # Some free models occasionally produce a malformed tool call. Ask again.
                messages.append({
                    "role": "user",
                    "content": "Your last tool call was malformed. Call a tool again with valid "
                               "JSON arguments, or answer if you already have enough evidence.",
                })
                continue
            raise

        if response.usage:
            tokens += response.usage.total_tokens
        message = response.choices[0].message

        # No tool requested: the model is giving its final answer.
        if not message.tool_calls:
            return AgentResult(message.content or "", steps, tokens)

        # Record the model's request, then run each tool it asked for.
        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in message.tool_calls
            ],
        })
        for call in message.tool_calls:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = None

            if arguments is None:
                result = "The arguments were not valid JSON. Try the call again."
                arguments = {}
            else:
                key = (call.function.name, json.dumps(arguments, sort_keys=True))
                if key in seen_calls:
                    result = (
                        "You already made this exact call and its result is above. Use that "
                        "result, make a different call, or answer now."
                    )
                else:
                    seen_calls.add(key)
                    result = run_tool(repo_id, call.function.name, arguments)

            step = ToolStep(call.function.name, arguments, result)
            steps.append(step)
            if on_step:
                on_step(step)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    # Out of steps: make the model answer with what it has found.
    text, used = _final_answer(client, repo_name, question, steps)
    return AgentResult(text, steps, tokens + used, hit_step_limit=True)