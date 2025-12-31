import typer
import os
from rich.console import Console
from rich.table import Table
from typing import Optional
from .core import (
    SUBJECT_CATEGORIES,
    SEMANTIC_CATEGORIES,
    CategoryType,
    fetch_category_words,
    save_words_to_csv,
    create_deck,
)

app = typer.Typer(help="AnkiFlow CLI: Download words and generate Anki decks.")
console = Console()


def print_category_table(title: str, categories: list, cat_type_label: str):
    table = Table(title=title)
    table.add_column("Index", justify="right", style="cyan", no_wrap=True)
    table.add_column("Type", style="green")
    table.add_column("Category Name", style="magenta")

    for idx, category in enumerate(categories):
        table.add_row(str(idx), cat_type_label, category.name)

    console.print(table)


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
    idx = subject_index if subject_index is not None else int(semantic_index)
    is_subject = subject_index is not None
    cat_type_str = "Subject" if is_subject else "Semantic"

    try:
        words = fetch_category_words(
            category_idx=idx,
            is_subject=is_subject,
            limit=limit,
            callback=lambda msg: typer.echo(msg),
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not words:
        typer.echo("No words found.")
        return

    category_enum = (SUBJECT_CATEGORIES if is_subject else SEMANTIC_CATEGORIES)[idx]
    filename = save_words_to_csv(words, category_enum.name)
    typer.echo(f"Successfully saved {len(words)} words to {filename}")


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

    try:
        create_deck(
            input_csv=input_csv,
            output_file=output_file,
            deck_title=deck_title,
            include_eng_kor=include_eng_kor,
            include_listening=include_listening,
            include_image_card=include_image_card,
            callback=lambda msg: typer.echo(msg),
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


def main():
    app()


if __name__ == "__main__":
    main()
