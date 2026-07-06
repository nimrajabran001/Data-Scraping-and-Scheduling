import ollama

from rag_api.config import LLM_MODEL
from rag_api.prompt import SYSTEM_PROMPT
from rag_api.weaviate_db import search
from rag_api.hybrid_search import hybrid_search
from rag_api.query_classifier import classify_query
from rag_api.hybrid_search import (
    hybrid_search,
    keyword_search
)

def build_context(results):

    context = []

    citations = []

    seen = set()

    for i, item in enumerate(results, start=1):

        context.append(f"""
Document {i}

Case:
{item.get("case","")}

Citation:
{item.get("citation","")}

Decision Date:
{item.get("decision_date","")}

Summary:
{item.get("summary","")}

Keywords:
{item.get("keywords","")}

Legal Issues:
{item.get("legal_issues","")}

Final Decision:
{item.get("final_decision","")}

Judgment:
{item.get("text","")}
""")

        key = (
            item.get("case"),
            item.get("citation")
        )

        if key not in seen:

            citations.append({

                "case": item.get("case",""),

                "citation": item.get("citation",""),

                "decision_date": item.get("decision_date",""),

                "pdf": item.get("pdf_url",""),

                "source": item.get("source_url","")

            })

            seen.add(key)

    return "\n".join(context), citations


def ask(question: str, top_k: int = 5):
    query_type = classify_query(question)

    print("Query Type:", query_type)
    """
    Retrieval-Augmented Generation (RAG).

    1. Embed question
    2. Retrieve top-k chunks
    3. Ask Ollama using retrieved context
    4. Return grounded answer with citations
    """


    # results = search(question, top_k)
    #
    # results = hybrid_search(
    #     question,
    #     limit=top_k
    # )

    query_type = classify_query(question)

    print("Query Type:", query_type)

    if query_type in ["citation", "case_number"]:

        results = keyword_search(
            question,
            limit=top_k
        )

    else:

        results = hybrid_search(
            question,
            limit=top_k
        )

    if not results:

        return {

            "question": question,

            "answer": "No relevant judgments were found.",

            "retrieved_documents": 0,

            "citations": []

        }

    context, citations = build_context(results)

    user_prompt = f"""
    You are an expert legal research assistant.

    Use ONLY the retrieved judgments.

    Never use outside knowledge.

    Never invent facts.

    If the answer is unavailable in the retrieved judgments, say so.

    If multiple judgments are retrieved:

    • Summarize each separately.
    • Do not merge facts from different cases.

    For broad queries like:

    murder
    contract
    bail

    summarize the relevant judgments.

    ==========================
    {context}
    ==========================

    Question:

    {question}

    Return:

    1. Direct answer

    2. Supporting reasoning

    3. Case names

    4. Neutral citations
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