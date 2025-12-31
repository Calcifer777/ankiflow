import os
import csv
import hashlib
import requests
import genanki
import importlib.resources
import krdict
import typer
from typing import Optional
from enum import Enum
from rich.console import Console
from rich.table import Table
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

# Anki/Media Config
MEDIA_DIR = "media_files"
QUERY_PREFIX = os.getenv("ANKIFLOW_QUERY_PREFIX", "")
QUERY_SUFFIX = os.getenv("ANKIFLOW_QUERY_SUFFIX", "")

# Fixed Retry Settings
MAX_RETRIES = 3
INITIAL_WAIT = 5

# Build stable lists for each type
SUBJECT_CATEGORIES = [m for m in krdict.SubjectCategory]
SEMANTIC_CATEGORIES = [m for m in krdict.SemanticCategory]

app = typer.Typer(help="AnkiFlow CLI: Download words and generate Anki decks.")
console = Console()


class CategoryType(str, Enum):
    subject = "subject"
    semantic = "semantic"
    all = "all"


# --- UTILS (from main.py) ---
CSS_STYLE = importlib.resources.files("ankiflow").joinpath("style.css").read_text()


def get_deterministic_id(string: str) -> int:
    """Generate a unique but stable ID for genanki."""
    return int(hashlib.sha256(string.encode()).hexdigest(), 16) % (10**10)


def ensure_media_dir():
    if not os.path.exists(MEDIA_DIR):
        os.makedirs(MEDIA_DIR)


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


def print_category_table(title: str, categories: list, cat_type_label: str):
    table = Table(title=title)
    table.add_column("Index", justify="right", style="cyan", no_wrap=True)
    table.add_column("Type", style="green")
    table.add_column("Category Name", style="magenta")

    for idx, category in enumerate(categories):
        table.add_row(str(idx), cat_type_label, category.name)

    console.print(table)


# --- COMMANDS ---


@app.command(name="list-categories")
def list_categories(
    category_type: CategoryType = typer.Option(
        CategoryType.all,
        "--type",
        "-t",
        help="Filter by category type (subject, semantic, or all).",
    ),
):
    """
    List available KRDict categories (Subject and Semantic) with their index.
    """
    if category_type in (CategoryType.subject, CategoryType.all):
        print_category_table("Subject Categories", SUBJECT_CATEGORIES, "Subject")
        if category_type == CategoryType.all:
            console.print()  # Add spacing

    if category_type in (CategoryType.semantic, CategoryType.all):
        print_category_table("Semantic Categories", SEMANTIC_CATEGORIES, "Semantic")


@app.command()
def download(
    subject_index: Optional[int] = typer.Option(
        None, "--subject", "-s", help="Index of the Subject category."
    ),
    semantic_index: Optional[int] = typer.Option(
        None, "--semantic", "-m", help="Index of the Semantic category."
    ),
    limit: int = typer.Option(
        100, "--limit", "-l", help="Maximum number of words to download."
    ),
):
    """
    Download a word collection from KRDict. You must specify EXACTLY ONE of --subject or --semantic.
    """
    # Mutually exclusive check
    if not bool(subject_index) ^ bool(semantic_index):
        typer.echo(
            "Error: Please provide only one of --subject or --semantic, not both.",
            err=True,
        )
        raise typer.Exit(1)

    # Resolve category
    if subject_index is not None:
        idx, categories, cat_type_str, is_subject = (
            subject_index,
            SUBJECT_CATEGORIES,
            "Subject",
            True,
        )
    elif semantic_index is not None:
        idx, categories, cat_type_str, is_subject = (
            semantic_index,
            SEMANTIC_CATEGORIES,
            "Semantic",
            False,
        )

    if idx < 0 or idx >= len(categories):
        typer.echo(
            f"Error: Invalid {cat_type_str.lower()} index {idx}. Valid range: 0-{len(categories)-1}",
            err=True,
        )
        raise typer.Exit(1)

    category_enum = categories[idx]

    name = category_enum.name
    typer.echo(
        f"Starting download for {name} ({cat_type_str}) [Index: {subject_index if is_subject else semantic_index}]..."
    )

    all_words = []
    page = 1
    per_page = 100

    while len(all_words) < limit:
        typer.echo(f"Fetching page {page} for {name}...")

        scraper_fun = (
            krdict.scraper.fetch_subject_category_words
            if is_subject
            else krdict.scraper.fetch_semantic_category_words
        )
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
            typer.echo(f"Error fetching from KRDict: {e}", err=True)
            break

    if not all_words:
        typer.echo(f"No words found for category: {name}")
        return

    os.makedirs("collections", exist_ok=True)
    filename = f"collections/{name.lower()}.csv"

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["english", "korean", "image_query", "definition"]
        )
        writer.writeheader()
        writer.writerows(all_words)

    typer.echo(f"Successfully saved {len(all_words)} words to {filename}")


@app.command(name="generate-anki")
def generate_anki(
    input_csv: str = typer.Option("words.csv", "--input", "-i", help="Input CSV file."),
    deck_title: str = typer.Option(
        "My Korean Deck", "--title", "-t", help="Title of the Anki deck."
    ),
    output_file: str = typer.Option(
        "deck.apkg", "--output", "-o", help="Output filename."
    ),
    include_eng_kor: bool = typer.Option(
        True, "--eng-kor/--no-eng-kor", help="Include English -> Korean card."
    ),
    include_listening: bool = typer.Option(
        True, "--listening/--no-listening", help="Include Listening card."
    ),
    include_image_card: bool = typer.Option(
        False, "--image-card/--no-image-card", help="Include Image -> Korean card."
    ),
):
    """
    Generate an Anki deck (.apkg) from a CSV file.
    """
    if not os.path.exists(input_csv):
        typer.echo(f"Error: Input file '{input_csv}' not found.", err=True)
        raise typer.Exit(1)

    ensure_media_dir()

    model_id = get_deterministic_id(deck_title + "_model_v1")
    deck_id = get_deterministic_id(deck_title + "_deck_v1")

    templates = []
    if include_eng_kor:
        templates.append(
            {
                "name": "English -> Korean",
                "qfmt": '<div class="english">{{English}}</div>',
                "afmt": '{{FrontSide}}<hr id="answer"><div class="korean">{{Korean}}<br>{{Audio}}</div>',
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
        typer.echo(
            "Error: No templates selected. Use flags to enable at least one card type.",
            err=True,
        )
        raise typer.Exit(1)

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

    typer.echo(f"Processing CSV: {input_csv}...")

    with open(input_csv, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            eng = row.get("english", "")
            kor = row.get("korean", "")

            if not eng or not kor:
                continue

            typer.echo(f"Processing: {eng} -> {kor}")

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
    typer.echo(f"\nCreated deck '{output_file}' with {len(deck.notes)} notes.")


def main():
    app()


if __name__ == "__main__":
    main()
