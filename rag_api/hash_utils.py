import hashlib


def calculate_record_hash(record: dict) -> str:
    """
    Generate a hash representing the content of a judgment.

    If any important field changes,
    the hash changes as well.
    """

    content = (
        record.get("case", "")
        + record.get("remarks", "")
        + record.get("category", "")
        + record.get("decision_date", "")
        + record.get("phc_neutral_citation", "")
    )

    return hashlib.md5(
        content.encode("utf-8")
    ).hexdigest()