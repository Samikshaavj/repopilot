from app.config import LLM_MODEL
from app.llm import get_client

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Add two numbers together.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            },
        },
    }
]

client = get_client()
response = client.chat.completions.create(
    model=LLM_MODEL,
    messages=[{"role": "user", "content": "What is 17 plus 25? Use the tool."}],
    tools=TOOLS,
)

message = response.choices[0].message
if message.tool_calls:
    call = message.tool_calls[0]
    print("The model asked for a tool:", call.function.name, call.function.arguments)
else:
    print("No tool call. The model said:", message.content)

print("Tokens used:", response.usage.total_tokens)