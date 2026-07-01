import ollama

from rag_api.config import LLM_MODEL
from rag_api.prompt import SYSTEM_PROMPT
from rag_api.weaviate_db import search


def build_context(results):
    """
    Build LLM context and collect unique citations.
    """

    context = []
    citations = []
    seen = set()

    for i, item in enumerate(results, start=1):

        context.append(
f"""
Document {i}

Case:
{item.get("case", "")}

Neutral Citation:
{item.get("citation", "")}

Decision Date:
{item.get("decision_date", "")}

Judgment:
{item.get("text", "")}
"""
        )

        key = (
            item.get("case", ""),
            item.get("citation", "")
        )

        if key not in seen:

            seen.add(key)

            citations.append({

                "case": item.get("case", ""),

                "citation": item.get("citation", ""),

                "decision_date": item.get("decision_date", ""),

                "pdf": item.get("pdf_url", ""),

                "source": item.get("source_url", "")

            })

    return "\n\n".join(context), citations


def ask(question: str, top_k: int = 5):
    """
    Retrieval-Augmented Generation (RAG).

    1. Embed question
    2. Retrieve top-k chunks
    3. Ask Ollama using retrieved context
    4. Return grounded answer with citations
    """

    results = search(question, top_k)

    if not results:

        return {

            "question": question,

            "answer": "No relevant judgments were found.",

            "retrieved_documents": 0,

            "citations": []

        }

    context, citations = build_context(results)

    user_prompt = f"""
You have been provided with relevant excerpts from Peshawar High Court judgments.

Answer ONLY using these excerpts.

If the information is insufficient, clearly state that the retrieved judgments do not contain enough information.

==========================
{context}
==========================

Question:
{question}

Requirements:

- Give a clear legal answer.
- Do not invent facts.
- Summarize where appropriate.
- Mention the relevant case name and neutral citation at the end.
"""

    response = ollama.chat(

        model=LLM_MODEL,

        messages=[

            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },

            {
                "role": "user",
                "content": user_prompt
            }

        ]

    )

    answer = response["message"]["content"].strip()

    return {

        "question": question,

        "answer": answer,

        "retrieved_documents": len(results),

        "citations": citations

    }


def chat_with_documents(question: str, top_k: int = 5):
    """
    Wrapper used by FastAPI endpoint.
    """
    return ask(question, top_k)