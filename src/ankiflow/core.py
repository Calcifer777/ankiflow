import os
import csv
import hashlib
import requests
import genanki
import importlib.resources
import krdict
from typing import Optional, Callable, List, Dict
from enum import Enum
from dotenv import load_dotenv
from gtts import gTTS
from ddgs import DDGS
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_result,
    retry_if_exception_type,
)
from time import sleep

# --- CONFIGURATION & CONSTANTS ---

load_dotenv()

# KRDict Config
API_KEY = os.getenv("KR_DICT_API_KEY")
if API_KEY:
    krdict.set_key(API_KEY)


def set_api_key(key: str):
    """Update the KRDict API key dynamically."""
    global API_KEY
    API_KEY = key
    krdict.set_key(key)


# Anki/Media Config
def get_media_dir() -> str:
    # Priority: FLET_APP_STORAGE_TEMP
    temp_dir = os.getenv("FLET_APP_STORAGE_TEMP")
    if not temp_dir:
        temp_dir = "media_files"
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

MEDIA_DIR = get_media_dir()
QUERY_PREFIX = os.getenv("ANKIFLOW_QUERY_PREFIX", "")
QUERY_SUFFIX = os.getenv("ANKIFLOW_QUERY_SUFFIX", "")

# Fixed Retry Settings
MAX_RETRIES = 3
INITIAL_WAIT = 5

# Build stable lists for each type
SUBJECT_CATEGORIES = [m for m in krdict.SubjectCategory]
SEMANTIC_CATEGORIES = [m for m in krdict.SemanticCategory]


class CategoryType(str, Enum):
    subject = "subject"
    semantic = "semantic"
    all = "all"


# Load CSS
try:
    CSS_STYLE = importlib.resources.files("ankiflow").joinpath("style.css").read_text()
except Exception:
    CSS_STYLE = ""  # Fallback if resource not found immediately (e.g. dev mode issues)


def get_deterministic_id(string: str) -> int:
    """Generate a unique but stable ID for genanki."""
    return int(hashlib.sha256(string.encode()).hexdigest(), 16) % (10**10)


@retry(
    retry=(
        retry_if_result(lambda res: res is not None and res.status_code == 429)
        | retry_if_exception_type(requests.RequestException)
    ),
    wait=wait_exponential(multiplier=INITIAL_WAIT, min=INITIAL_WAIT, max=60),
    stop=stop_after_attempt(MAX_RETRIES + 1),
    reraise=True,
)
def _fetch_url(url, headers=None, params=None):
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    if resp.status_code == 429:
        print(f"Rate limited. Retrying...")
    return resp


def get_image_url(query: str) -> str | None:
    search_query = f"{QUERY_PREFIX} {query} {QUERY_SUFFIX}".strip()
    try:
        with DDGS() as ddgs:
            results = ddgs.images(
                query=search_query,
                region="wt-wt",
                safesearch="on",
                size="Small",
                max_results=1,
            )
            if results:
                return results[0]["image"]
    except Exception as e:
        print(f"Failed to search DuckDuckGo for '{query}': {e}")

    return None


def download_file(url: str, filename: str) -> str | None:
    path = os.path.join(MEDIA_DIR, filename)
    if os.path.exists(path):
        return path

    try:
        response = _fetch_url(url)
        if response.status_code == 200:
            with open(path, "wb") as f:
                f.write(response.content)
            return path
    except Exception as e:
        print(f"Failed to download {filename} after retries: {e}")
    return None


def generate_audio_file(text: str, filename: str, lang: str = "ko") -> str | None:
    path = os.path.join(MEDIA_DIR, filename)
    if os.path.exists(path):
        return path

    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(path)
        return path
    except Exception as e:
        print(f"Error generating audio for {text}: {e}")
    return None


def fetch_category_words(
    category_idx: int,
    is_subject: bool,
    limit: int = 100,
    callback: Callable[[str], None] = None,
) -> List[Dict[str, str]]:
    """
    Fetches words from KRDict based on category index.
    """
    if callback is None:

        def callback(s):
            pass

    categories = SUBJECT_CATEGORIES if is_subject else SEMANTIC_CATEGORIES
    if category_idx < 0 or category_idx >= len(categories):
        raise ValueError(f"Invalid index {category_idx}")

    category_enum = categories[category_idx]
    name = category_enum.name
    callback(f"Starting download for {name}...")

    all_words = []
    page = 1
    per_page = 100

    scraper_fun = (
        krdict.scraper.fetch_subject_category_words
        if is_subject
        else krdict.scraper.fetch_semantic_category_words
    )

    while len(all_words) < limit:
        callback(f"Fetching page {page} for {name}...")

        try:
            response = scraper_fun(
                category=category_enum,
                page=page,
                per_page=per_page,
                translation_language=krdict.TranslationLanguage.ENGLISH,
            )

            if not response or not response.data or not response.data.results:
                break

            results = response.data.results
            for item in results:
                word = item.word
                translation = ""
                definition = ""

                if item.definitions:
                    for dfn in item.definitions:
                        if dfn.translations:
                            for trans in dfn.translations:
                                if trans.language in ["영어", "English"]:
                                    translation = trans.word
                                    definition = trans.definition
                                    break
                            if translation:
                                break

                    if not definition and item.definitions:
                        definition = item.definitions[0].definition

                if translation:
                    simple_translation = translation.split(",")[0].split(";")[0].strip()
                    all_words.append(
                        {
                            "english": simple_translation,
                            "korean": word,
                            "image_query": simple_translation,
                            "definition": definition,
                        }
                    )

                if len(all_words) >= limit:
                    break

            if len(results) < per_page:
                break
            page += 1

        except Exception as e:
            callback(f"Error fetching from KRDict: {e}")
            break

    return all_words


def get_app_data_dir() -> str:
    """Returns the path to the application data directory."""
    # Priority: FLET_APP_STORAGE_DATA (set by Flet in packaged apps)
    base_dir = os.getenv("FLET_APP_STORAGE_DATA")
    
    if not base_dir:
        # Fallback for development: ~/.ankiflow
        base_dir = os.path.join(os.path.expanduser("~"), ".ankiflow")
    
    collections_dir = os.path.join(base_dir, "collections")
    os.makedirs(collections_dir, exist_ok=True)
    return collections_dir


def save_words_to_csv(words: List[Dict[str, str]], category_name: str) -> str:
    collections_dir = get_app_data_dir()
    filename = os.path.join(collections_dir, f"{category_name.lower()}.csv")

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["english", "korean", "image_query", "definition"]
        )
        writer.writeheader()
        writer.writerows(words)
    return filename


def create_deck(


    input_csv: str,


    output_file: str,


    deck_title: str,


    include_eng_kor: bool = True,


    include_listening: bool = True,


    include_image_card: bool = False,


    callback: Callable[[str], None] = None,


):


    if callback is None:


        def callback(s): pass


    


    model_id = get_deterministic_id(deck_title + "_model_v1")



    deck_id = get_deterministic_id(deck_title + "_deck_v1")

    templates = []
    if include_eng_kor:
        templates.append(
            {
                "name": "English -> Korean",
                "qfmt": '<div class="english">{{English}}</div>',
                "afmt": '{{FrontSide}}<hr id="answer"><div class="korean">{{Korean}}<br>{{Audio}}<br>{{Image}}</div>',
            }
        )
    if include_listening:
        templates.append(
            {
                "name": "Listening (Audio -> English + Audio)",
                "qfmt": "{{Audio}}",
                "afmt": '{{FrontSide}}<hr id="answer"><div class="english">{{English}}</div><div class="korean">{{Korean}}</div>',
            }
        )
    if include_image_card:
        templates.append(
            {
                "name": "Image -> Korean + Audio + English",
                "qfmt": "{{Image}}",
                "afmt": '{{FrontSide}}<hr id="answer"><div class="korean">{{Korean}} ({{English}})</div><br>{{Audio}}',
            }
        )

    if not templates:
        raise ValueError("No templates selected.")

    my_model = genanki.Model(
        model_id,
        "AnkiFlow Bidirectional Model",
        fields=[
            {"name": "English"},
            {"name": "Korean"},
            {"name": "Audio"},
            {"name": "Image"},
        ],
        templates=templates,
        css=CSS_STYLE,
    )

    deck = genanki.Deck(deck_id, deck_title)
    media_files = []

    callback(f"Processing CSV: {input_csv}")

    with open(input_csv, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            eng = row.get("english", "")
            kor = row.get("korean", "")

            if not eng or not kor:
                continue

            callback(f"Processing: {eng} -> {kor}")

            safe_name = eng.replace(" ", "_").lower()

            # 1. Audio
            audio_file = f"ko_{safe_name}.mp3"
            audio_path = generate_audio_file(kor, audio_file)
            if audio_path:
                media_files.append(audio_path)

            # 2. Image (Only if image card is enabled)
            image_str = ""
            if include_image_card:
                image_file = f"img_{safe_name}.jpg"
                image_path_local = os.path.join(MEDIA_DIR, image_file)

                # Check if image exists, otherwise download
                if os.path.exists(image_path_local):
                    media_files.append(image_path_local)
                    image_str = f'<img src="{image_file}">'
                else:
                    image_url = get_image_url(eng)
                    if image_url:
                        image_path = download_file(image_url, image_file)
                        if image_path:
                            media_files.append(image_path)
                            image_str = f'<img src="{image_file}">'

            # 3. Add Note
            note = genanki.Note(
                model=my_model,
                fields=[
                    eng,
                    kor,
                    f"[sound:{audio_file}]",
                    image_str,
                ],
            )
            deck.add_note(note)

    package = genanki.Package(deck)
    package.media_files = media_files
    package.write_to_file(output_file)
    callback(f"Created deck '{output_file}' with {len(deck.notes)} notes.")
