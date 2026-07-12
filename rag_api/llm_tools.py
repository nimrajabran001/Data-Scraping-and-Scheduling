"""
LLM tool-calling wrapper (Section 5).

Uses Ollama's native tool-calling support (available on models like
llama3.1/3.2, qwen2.5, mistral-nemo — NOT phi3:mini, which does not
support tools reliably; switch LLM_MODEL for the chat layer if needed,
see DECISIONS.md).

The LLM decides on its own turn whether to call search_judgments. We do
NOT force a call — Section 5.2 requires greetings/small talk/off-domain
questions and result follow-ups to be handled without a fresh search.
"""

import json
import logging

import ollama

from rag_api.search_tool import search_judgments, SEARCH_JUDGMENTS_TOOL_SCHEMA

logger = logging.getLogger(__name__)

CHAT_MODEL = "llama3.1"  # override with a tool-calling-capable model

SYSTEM_PROMPT = """
You are a research assistant for Peshawar High Court judgments.

You have access to a tool called search_judgments. Call it when the user
asks about a specific judgment, citation, case number, judge, party name,
statute/section, or a legal question that plausibly has an answer in PHC
case law.

Do NOT call the tool for:
- greetings or small talk
- follow-up questions about a result you already returned this turn
  (answer from the conversation context instead)
- questions clearly unrelated to Pakistani law (answer briefly and
  redirect the user back to what you can help with)

If the tool returns status "not_applicable" or "no_results", relay that
message to the user in your own words — do not invent a judgment.

When you do get judgment results, cite the case name and neutral citation
for every claim you make about it. Never state facts, judges, dates, or
outcomes that are not present in the tool result.
"""

TOOLS = [SEARCH_JUDGMENTS_TOOL_SCHEMA]


def _execute_tool_call(tool_call: dict) -> dict:
    """Dispatch a single tool call from the model to our Python function."""

    name = tool_call["function"]["name"]
    raw_args = tool_call["function"].get("arguments", {})

    if isinstance(raw_args, str):
        raw_args = json.loads(raw_args)

    if name != "search_judgments":
        return {"status": "error", "message": f"Unknown tool: {name}"}

    logger.info(f"Tool call: search_judgments({raw_args})")

    return search_judgments(**raw_args)


def chat_turn(messages: list) -> tuple[str, list]:
    """
    Run one assistant turn given the full message history (list of
    {"role": ..., "content": ...} dicts, OpenAI/Ollama-style).

    Returns (assistant_text, updated_messages) so the caller (CLI/web UI)
    can keep accumulating conversation state across turns, satisfying the
    multi-turn / follow-up requirement in Section 5.3.
    """

    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    response = ollama.chat(
        model=CHAT_MODEL,
        messages=full_messages,
        tools=TOOLS,
    )

    message = response["message"]
    tool_calls = message.get("tool_calls") or []

    if not tool_calls:
        # No tool call this turn -> greeting, small talk, follow-up
        # answered from context, or a graceful off-domain reply.
        assistant_text = message.get("content", "")
        messages.append({"role": "assistant", "content": assistant_text})
        return assistant_text, messages

    # Model asked to call one or more tools. Execute each, feed results
    # back, then ask the model to produce the final natural-language reply.
    messages.append(
        {
            "role": "assistant",
            "content": message.get("content", ""),
            "tool_calls": tool_calls,
        }
    )

    for tool_call in tool_calls:
        result = _execute_tool_call(tool_call)

        messages.append(
            {
                "role": "tool",
                "content": json.dumps(result),
            }
        )

    follow_up = ollama.chat(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    )

    assistant_text = follow_up["message"].get("content", "")
    messages.append({"role": "assistant", "content": assistant_text})

    return assistant_text, messages
