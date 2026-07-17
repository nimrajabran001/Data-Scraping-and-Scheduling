from dotenv import load_dotenv
load_dotenv()
 
from rag_api.pipeline import run_ingestion
from storage import JSON_FILE
 
if __name__ == "__main__":
    print(f"Running ingestion against: {JSON_FILE}")
    summary = run_ingestion(JSON_FILE)
    print("\nDone.")
    print(summary)
 