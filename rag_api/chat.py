import ollama

from rag_api.config import LLM_MODEL
from rag_api.prompt import SYSTEM_PROMPT
from rag_api.query_classifier import classify_query
from rag_api.search_tool import _make_similarity_fn
from rag_api.hybrid_search import hybrid_search, keyword_search


def build_context(results):
    """
    Build context for the LLM from retrieved judgments.
    """

    context = []
    citations = []
    seen = set()

    for i, item in enumerate(results, start=1):

        context.append(f"""
Document {i}

Case:
{item.get("case", "")}

Neutral Citation:
{item.get("citation", "")}

Decision Date:
{item.get("decision_date", "")}

Summary:
{item.get("summary", "")}

Final Decision:
{item.get("final_decision", "")}

Legal Issues:
{item.get("legal_issues", "")}

Keywords:
{item.get("keywords", "")}

Judgment Excerpt:
{item.get("text", "")[:800]}
""")

        key = (item.get("case", ""), item.get("citation", ""))

        if key not in seen:
            citations.append({
                "case": item.get("case", ""),
                "citation": item.get("citation", ""),
                "decision_date": item.get("decision_date", ""),
                "pdf": item.get("pdf_url", ""),
                "source": item.get("source_url", ""),
            })
            seen.add(key)

    return "\n".join(context), citations


def ask(question: str, top_k: int = 5):

    # --------------------------------------------------------
    # classify_query now returns {"relevance": ..., "query_type": ...}
    # (Section 4/5 relevance gate + Section 2/3 strategy routing)
    # --------------------------------------------------------
    classification = classify_query(question, embedding_similarity_fn=_make_similarity_fn())

    query_type = classification["query_type"]
    relevance = classification["relevance"]

    print(f"\nRelevance: {relevance} | Query Type: {query_type}")

    if relevance == "irrelevant":
        return {
            "question": question,
            "answer": "This assistant only answers questions about Peshawar High Court judgments.",
            "retrieved_documents": 0,
            "citations": [],
        }

    if query_type in ["citation", "case_number", "case_name"]:
        print("Using BM25 Keyword Search...")
        results = keyword_search(question, limit=top_k)
    else:
        print("Using Hybrid Search...")
        results = hybrid_search(question, limit=top_k)

    if not results:
        return {
            "question": question,
            "answer": "No relevant judgments were found.",
            "retrieved_documents": 0,
            "citations": [],
        }

    print("\nRetrieved Documents\n")

    for i, r in enumerate(results, start=1):
        print("=" * 80)
        print(f"Rank {i}")
        print("Case:", r.get("case"))
        print("Citation:", r.get("citation"))
        print("Score:", r.get("fusion_score", r.get("score")))

    context, citations = build_context(results)

    hedge = (
        "\n\nNote: this query was ambiguous relative to the corpus — "
        "double-check the case details below before relying on them."
        if relevance == "ambiguous"
        else ""
    )

    user_prompt = f"""
You are an expert legal research assistant for the Peshawar High Court.

You MUST answer ONLY from the retrieved judgments below.

==========================
Retrieved Judgments
==========================

{context}

==========================

Question:

{question}

Instructions:

1. Use ONLY the retrieved judgments.
2. Never use outside legal knowledge.
3. Never invent facts, judges, dates, punishments or legal conclusions.
4. If the retrieved judgments do not contain enough information, clearly say:
"The retrieved judgments do not contain enough information to answer this question."
5. If the question asks for a legal definition and the judgments merely discuss
that issue without defining it, state:
"The retrieved judgments discuss this issue but do not provide a legal definition."
6. Treat every judgment independently.
7. Never merge facts from different cases.
8. Ignore citations to other judgments unless the user explicitly asks about those cited cases.
9. Base your answer on the retrieved judgment itself.
10. For broad topics, summarize the relevant judgments separately.
11. If the user asks about a specific case or person, focus only on that judgment,
summarize facts/legal issue/reasoning, and state the final decision.

Return the answer in the following format:

Answer:
<direct answer>

Supporting Judgments:

- Case Name
- Neutral Citation
- Brief explanation

Only include judgments that directly support your answer.{hedge}
"""

    response = ollama.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    answer = response["message"]["content"].strip()

    return {
        "question": question,
        "answer": answer,
        "retrieved_documents": len(results),
        "citations": citations,
    }


def chat_with_documents(question: str, top_k: int = 5):
    """
    FastAPI wrapper.
    """
    return ask(question, top_k)
