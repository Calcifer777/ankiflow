# AnkiFlow

AnkiFlow is a CLI tool designed to streamline the creation of Korean language learning decks for Anki. It automates the process of fetching vocabulary collections, sourcing relevant media from DuckDuckGo Search, generating audio pronunciations, and packaging everything into a ready-to-import `.apkg` file.

## Features

-   **Smart Vocabulary Fetching**: Download curated word lists from KRDict based on **Subject** (e.g., "Greeting", "Ordering Food") or **Semantic** (e.g., "Body Parts", "Emotions") categories.
-   **Automated Media**:
    -   **Images**: Automatically fetches relevant images for each word using DuckDuckGo Search.
    -   **Audio**: Generates Korean audio pronunciation (TTS) for every word.
-   **Anki Integration**: Generates fully formatted Anki decks (`.apkg`) with a clean, bidirectional card design.
-   **Unified CLI**: Simple, intuitive command-line interface powered by Typer.

## Prerequisites

-   Python 3.13 or higher.
-   **KRDict API Key**: Required to access the Korean dictionary data (obtainable from the [National Institute of Korean Language](https://krdict.korean.go.kr/eng/openApi/openApiRegister#)).

## Installation

You can install the dependencies using `uv` (recommended) or `pip`.

### Using uv
```bash
uv sync
```

### Using pip
```bash
pip install .
```

## Configuration

Create a `.env` file in the root directory:

```env
# Required for fetching words
KR_DICT_API_KEY=your_krdict_api_key_here
```

## Usage

### GUI (Recommended)

Launch the graphical interface for an easy, interactive experience.

```bash
ankiflow-gui
```
(Or `uv run ankiflow-gui` if using uv)

### CLI

The CLI is accessed via the `ankiflow` command.

### 1. List Available Categories

View all available Subject and Semantic categories with their corresponding indices.

```bash
ankiflow list-categories
```

Filter by type:
```bash
ankiflow list-categories --type subject
ankiflow list-categories --type semantic
```

### 2. Download Vocabulary

Fetch words from a specific category using its index. You must specify either `--subject` (`-s`) or `--semantic` (`-m`).

**Example: Download "Elementary Greeting" (Subject Index 0)**
```bash
ankiflow download --subject 0 --limit 20
```

**Example: Download "Body Parts" (Semantic Index 2)**
```bash
ankiflow download --semantic 2 --limit 50
```

This will save a CSV file (e.g., `collections/elementary_greeting.csv`) containing the English definition, Korean word, and other metadata.

### 3. Generate Anki Deck

Create an Anki deck from the downloaded CSV file. This step will also download images and generate audio files.

```bash
ankiflow generate-anki --input collections/elementary_greeting.csv --output "Korean Greetings.apkg" --title "Korean Greetings"
```

Once complete, simply double-click the `.apkg` file to import it into Anki!

## Example Workflow

Here is a complete workflow to create a deck for "Ordering Food":

1.  **Find the category index:**
    ```bash
    ankiflow list-categories --type subject
    # Locate "ELEMENTARY_ORDERING_FOOD" (Assume Index 8)
    ```

2.  **Download the words:**
    ```bash
    ankiflow download --subject 8 --limit 30
    ```

3.  **Generate the deck:**
    ```bash
    ankiflow generate-anki --input collections/elementary_ordering_food.csv --output food_deck.apkg --title "Ordering Food"
    ```
