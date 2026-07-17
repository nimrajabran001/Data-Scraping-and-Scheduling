"""
LLM tool-calling wrapper.

Uses Ollama's native tool-calling support (available on models like
llama3.1/3.2, qwen2.5, mistral-nemo -- NOT phi3:mini, which does not
support tools reliably; switch CHAT_MODEL if needed, see DECISIONS.md).

Revision: fetch-first with relevance evaluation and retry.

Whenever the model calls search_judgments, we no longer accept whatever
comes back on the first try. We evaluate the result for relevance
(status == "ok" and a top score above RELEVANCE_SCORE_THRESHOLD); if it
isn't relevant, we retry with a widened search (bigger top_k, forced
hybrid strategy) up to MAX_FETCH_ATTEMPTS times total. If none of the
attempts produce a relevant result, we stop retrying and instruct the
model to answer the user's message normally instead of forcing a
grounded-but-empty response.
"""

import json
import logging

import ollama

from rag_api.search_tool import search_judgments, SEARCH_JUDGMENTS_TOOL_SCHEMA

logger = logging.getLogger(__name__)

CHAT_MODEL = "llama3.1"  # override with a tool-calling-capable model

MAX_FETCH_ATTEMPTS = 3
RELEVANCE_SCORE_THRESHOLD = 0.35  # keep in sync with search_config thresholds

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
message to the user in your own words -- do not invent a judgment.

When you do get judgment results, cite the case name and neutral citation
for every claim you make about it. Never state facts, judges, dates, or
outcomes that are not present in the tool result.
"""

TOOLS = [SEARCH_JUDGMENTS_TOOL_SCHEMA]


def _top_score(result: dict) -> float:
    results = result.get("results") or []

    if not results:
        return -1.0

    return results[0].get("score", 0.0) or 0.0


def _is_relevant(result: dict) -> bool:
    """Decide whether a search_judgments() result is good enough to ground an answer on."""

    if result.get("status") != "ok":
        return False

    if not result.get("results"):
        return False

    return _top_score(result) >= RELEVANCE_SCORE_THRESHOLD


def _fetch_relevant_judgments(query: str, base_args: dict) -> tuple[dict, int, bool]:
    """
    Call search_judgments up to MAX_FETCH_ATTEMPTS times, widening the
    search each time the result isn't relevant enough.

    Returns (best_result, attempts_used, found_relevant).
    """

    args = dict(base_args)
    args["query"] = query

    best_result = None
    best_score = -1.0

    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        result = search_judgments(**args)

        logger.info(
            f"Fetch attempt {attempt}/{MAX_FETCH_ATTEMPTS} for {query!r}: "
            f"status={result.get('status')} top_score={_top_score(result):.3f}"
        )

        if _is_relevant(result):
            return result, attempt, True

        score = _top_score(result)

        if score > best_score:
            best_score = score
            best_result = result

        # Widen the net for the next attempt: pull more candidates and
        # force hybrid so both rankers get a vote, in case the model's
        # chosen strategy was too narrow.
        args["top_k"] = min(args.get("top_k", 5) + 5, 20)
        args["strategy"] = "hybrid"

    return (
        best_result or {"status": "no_results", "message": "No relevant judgments found."},
        MAX_FETCH_ATTEMPTS,
        False,
    )


def _execute_tool_call(tool_call: dict) -> tuple[dict, bool]:
    """Dispatch a single tool call from the model to our Python function, with retry."""

    name = tool_call["function"]["name"]
    raw_args = tool_call["function"].get("arguments", {})

    if isinstance(raw_args, str):
        raw_args = json.loads(raw_args)

    if name != "search_judgments":
        return {"status": "error", "message": f"Unknown tool: {name}"}, False

    raw_args = dict(raw_args)
    query = raw_args.pop("query", "")

    result, attempts_used, found_relevant = _fetch_relevant_judgments(query, raw_args)

    logger.info(
        f"Tool call resolved after {attempts_used} attempt(s), relevant={found_relevant}"
    )

    result["_attempts_used"] = attempts_used

    return result, found_relevant


def chat_turn(messages: list) -> tuple[str, list]:
    """
    Run one assistant turn given the full message history (list of
    {"role": ..., "content": ...} dicts, OpenAI/Ollama-style).

    Returns (assistant_text, updated_messages) so the caller (CLI/web UI)
    can keep accumulating conversation state across turns.
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

    # Model asked to call one or more tools. Execute each with the
    # fetch-and-evaluate retry loop, feed results back, then ask the
    # model to produce the final natural-language reply.
    messages.append(
        {
            "role": "assistant",
            "content": message.get("content", ""),
            "tool_calls": tool_calls,
        }
    )

    any_relevant = False

    for tool_call in tool_calls:
        result, found_relevant = _execute_tool_call(tool_call)

        any_relevant = any_relevant or found_relevant

        messages.append(
            {
                "role": "tool",
                "content": json.dumps(result),
            }
        )

    if not any_relevant:
        # All tool calls exhausted MAX_FETCH_ATTEMPTS without finding
        # anything relevant -- stop trying to ground the answer and have
        # the model respond to the user's message directly instead.
        messages.append(
            {
                "role": "system",
                "content": (
                    "No relevant judgments were found after multiple search "
                    "attempts. Answer the user's message directly and "
                    "briefly without referencing search or tool results, "
                    "and do not invent case law."
                ),
            }
        )

    follow_up = ollama.chat(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    )

    assistant_text = follow_up["message"].get("content", "")
    messages.append({"role": "assistant", "content": assistant_text})

    return assistant_text, messages