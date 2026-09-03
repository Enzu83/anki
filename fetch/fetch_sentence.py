import argparse
import json
import time
from pathlib import Path

import requests

from pipeline import JLPT_LEVELS, load_jlpt_data, is_jlpt_sentence


# ============================================================
# CONFIG
# ============================================================

TATOEBA_API = "https://api.tatoeba.org/v1/sentences"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "sentences"

TARGET_SENTENCES = 500

# Keep sentences reasonably short for reading practice.
MIN_WORDS = 2
MAX_WORDS = 15


# ============================================================
# TATOEBA
# ============================================================

def get_sentences(url=None, limit=100):
    """
    Retrieve Japanese sentences with English translations.

    Tatoeba's v1 API paginates via a cursor URL (`paging.next`) rather
    than a page number, so the first call builds the query from scratch
    and every subsequent call just follows that URL.
    """

    if url:
        response = requests.get(url, timeout=30)
    else:
        params = {
            "lang": "jpn",
            "sort": "random",
            "limit": limit,

            # Shorter sentences are more useful for this deck.
            "word_count": f"{MIN_WORDS}-{MAX_WORDS}",

            # Ask Tatoeba for translations.
            "showtrans": "all",
        }

        response = requests.get(
            TATOEBA_API,
            params=params,
            timeout=30,
        )

    response.raise_for_status()

    return response.json()


# ============================================================
# EXTRACT TRANSLATION
# ============================================================

def get_english_translation(item):
    """
    Extract an English translation if one is available.

    The exact response structure can vary depending on the
    API query/version, so this function is isolated here.
    """

    translations = item.get("translations", [])

    for group in translations:

        # Depending on the API response, translations may be
        # grouped.
        if isinstance(group, list):
            candidates = group
        else:
            candidates = [group]

        for translation in candidates:

            if translation.get("lang") == "eng":
                return translation.get("text")

    return None


# ============================================================
# FILTER
# ============================================================

def process_sentence(item, jlpt_data):
    """
    Returns (result, reason). `result` is None when the sentence is
    rejected; `reason` names which check rejected it ("kanji", "vocab",
    "grammar", or "empty"), for tracking where the pipeline is losing
    sentences.
    """

    sentence = item.get("text", "").strip()

    if not sentence:
        return None, "empty"

    # --------------------------------------------------------
    # 1. Kanji / vocabulary / grammar
    # --------------------------------------------------------

    accepted, reason, tokens = is_jlpt_sentence(sentence, jlpt_data)

    if not accepted:
        return None, reason

    # --------------------------------------------------------
    # 2. Translation
    # --------------------------------------------------------

    english = get_english_translation(item)

    result = {
        "id": item.get("id"),
        "japanese": sentence,
        "english": english,
        "tokens": tokens,
    }

    return result, None


# ============================================================
# MAIN
# ============================================================

def main(level):

    jlpt_data = load_jlpt_data(level)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"N{jlpt_data['level']}_sentences.json"

    results = []
    seen = set()
    rejections = {"empty": 0, "kanji": 0, "vocab": 0, "grammar": 0}

    next_url = None
    page = 1

    while len(results) < TARGET_SENTENCES:

        print(f"Downloading page {page}...")

        try:
            data = get_sentences(url=next_url)

        except requests.RequestException as e:
            print("Tatoeba request failed:", e)
            break

        sentences = data.get("data", [])

        if not sentences:
            print("No more sentences.")
            break

        accepted = 0

        for item in sentences:

            result, reason = process_sentence(item, jlpt_data)

            if result is None:
                rejections[reason] += 1
                continue

            japanese = result["japanese"]

            # Remove duplicates.
            if japanese in seen:
                continue

            seen.add(japanese)

            results.append(result)
            accepted += 1

            if len(results) >= TARGET_SENTENCES:
                break

        print(
            f"  received: {len(sentences)}"
            f" | accepted: {accepted}"
            f" | total: {len(results)}"
        )

        next_url = data.get("paging", {}).get("next")

        if not next_url:
            print("No more pages.")
            break

        page += 1

        # Don't hammer the API.
        time.sleep(0.3)

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            results,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(f"Saved {len(results)} sentences to {output_file}")
    print(f"Rejections: {rejections}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Fetch Tatoeba sentences filtered to a single JLPT level.",
    )
    parser.add_argument(
        "--level",
        choices=JLPT_LEVELS,
        default="5",
        help="JLPT level to fetch sentences for (1 = hardest, 5 = easiest). Default: 5.",
    )
    args = parser.parse_args()

    main(args.level)
