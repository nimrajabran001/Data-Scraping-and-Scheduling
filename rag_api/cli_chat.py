"""
Minimal CLI chat frontend for Stage 4.

Run:
    python cli_chat.py

Type your question. Type 'exit' to quit and save the transcript.

This satisfies Section 9's "minimal CLI or web UI ... Include a short
session transcript showing tool-call vs no-tool-call turns" requirement:
every turn is logged to transcript.json with whether a tool was called.
"""

import json
import sys
from datetime import datetime

from rag_api.llm_tools import chat_turn

TRANSCRIPT_PATH = "transcript.json"


def main():
    print("PHC Judgment Assistant (type 'exit' to quit)\n")

    messages = []
    transcript = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            break

        messages.append({"role": "user", "content": user_input})

        pre_call_len = len(messages)

        assistant_text, messages = chat_turn(messages)

        # Did a tool get called this turn? Check for a "tool" role message
        # added between the user's message and the final assistant reply.
        tool_called = any(
            m.get("role") == "tool" for m in messages[pre_call_len:]
        )

        print(f"\nAssistant: {assistant_text}\n")

        transcript.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "user": user_input,
                "assistant": assistant_text,
                "tool_called": tool_called,
            }
        )

    with open(TRANSCRIPT_PATH, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)

    print(f"\nTranscript saved to {TRANSCRIPT_PATH}")


if __name__ == "__main__":
    sys.exit(main())
