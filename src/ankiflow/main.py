import genanki
import os
import random
import requests
from gtts import gTTS
from dotenv import load_dotenv

# --- CONFIGURATION ---

# PASTE YOUR PEXELS API KEY HERE
assert load_dotenv()

PEXELS_API_KEY = os.environ["PEXELS_API_KEY"]
DECK_TITLE: str = "Korean Body Parts (Bidirectional)"
OUTPUT_FILENAME: str = "korean_body_parts_v2.apkg"

# Data structure: list of tuples (Search Query, Korean Translation)
BODY_PARTS: list[tuple[str, str]] = [
    ("Human Head", "머리"),
    ("Human Eye", "눈"),
    ("Human Nose", "코"),
    ("Human Mouth", "입"),
]

# Ensure media directory exists
if not os.path.exists("media_files"):
    os.makedirs("media_files")


def get_pexels_image_url(query: str) -> str | None:
    """
    Searches Pexels for a photo and returns the 'small' size URL.
    Returns None if no image is found or if an error occurs.
    """
    headers: dict[str, str] = {"Authorization": PEXELS_API_KEY}
    url: str = f"https://api.pexels.com/v1/search?query=human+{query}&per_page=1"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data: dict = response.json()

        if data.get("photos"):
            # Returning the small src URL
            return data["photos"][0]["src"]["small"]
        else:
            print(f"No results found on Pexels for: {query}")
            return None
    except Exception as e:
        print(f"Error searching Pexels for {query}: {e}")
        return None


def download_file(url: str, filename: str) -> str | None:
    """
    Downloads a file from a URL to the media_files directory.
    Returns the relative path to the file, or None if download fails.
    """
    path: str = f"media_files/{filename}"
    if os.path.exists(path):
        return path

    try:
        headers: dict[str, str] = {"Authorization": PEXELS_API_KEY}
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        with open(path, "wb") as f:
            f.write(response.content)
        print(f"Downloaded: {filename}")
        return path
    except Exception as e:
        print(f"Failed to download {filename}: {e}")
        return None


def generate_audio(korean_text: str, filename: str) -> str | None:
    """
    Generates an MP3 file using Google Text-to-Speech.
    Returns the relative path to the file.
    """
    path: str = f"media_files/{filename}"
    if not os.path.exists(path):
        try:
            tts = gTTS(text=korean_text, lang="ko")
            tts.save(path)
            print(f"Generated Audio: {filename}")
        except Exception as e:
            print(f"Error generating audio for {korean_text}: {e}")
            return None
    return path


# --- Anki Model Setup ---

# Unique IDs using standard python random
model_id: int = random.randrange(1 << 30, 1 << 31)
deck_id: int = random.randrange(1 << 30, 1 << 31)

css_style: str = """
.card {
 font-family: arial;
 font-size: 20px;
 text-align: center;
 color: black;
 background-color: white;
}
.korean {
 font-size: 30px;
 font-weight: bold;
 color: #000080;
 margin: 10px;
}
.english {
 font-size: 24px;
 margin-bottom: 10px;
 color: #333;
}
img {
  max-width: 300px; 
  max-height: 300px;
  margin-top: 15px;
  border-radius: 8px;
  box-shadow: 2px 2px 5px rgba(0,0,0,0.2);
}
"""

# We now define TWO templates in the templates list
my_model = genanki.Model(
    model_id,
    "Korean Body Parts Bidirectional",
    fields=[
        {"name": "English"},
        {"name": "Korean"},
        {"name": "Audio"},
        {"name": "Image"},
    ],
    templates=[
        # Card 1: English/Image -> Korean/Audio
        {
            "name": "Recall (Eng -> Kor)",
            "qfmt": '<div class="english">{{English}}</div><br>{{Image}}',
            "afmt": '{{FrontSide}}<hr id="answer"><div class="korean">{{Korean}}</div><br>{{Audio}}',
        },
        # Card 2: Korean/Audio -> English/Image (Reverse)
        {
            "name": "Listening (Kor -> Eng)",
            "qfmt": '<div class="korean">{{Korean}}</div><br>{{Audio}}',
            "afmt": '{{FrontSide}}<hr id="answer"><div class="english">{{English}}</div><br>{{Image}}',
        },
    ],
    css=css_style,
)

my_deck = genanki.Deck(deck_id, DECK_TITLE)
media_files_list: list[str] = []

# --- Main Logic ---

print("Starting deck generation...")

for search_query, kor_word in BODY_PARTS:
    # Simplify filename
    safe_name: str = search_query.replace("Human ", "").replace(" ", "_").lower()

    audio_filename: str = f"ko_{safe_name}.mp3"
    image_filename: str = f"img_{safe_name}.jpg"

    # 1. Generate Audio
    generate_audio(kor_word, audio_filename)
    media_files_list.append(f"media_files/{audio_filename}")

    # 2. Search and Download Image
    image_url: str | None = get_pexels_image_url(search_query)
    image_field_content: str = ""

    if image_url:
        download_path: str | None = download_file(image_url, image_filename)
        if download_path:
            media_files_list.append(download_path)
            image_field_content = f'<img src="{image_filename}">'

    # 3. Add Note
    # The note automatically creates 2 cards because the Model has 2 templates
    note = genanki.Note(
        model=my_model,
        fields=[
            search_query.replace("Human ", ""),  # English Field
            kor_word,  # Korean Field
            f"[sound:{audio_filename}]",  # Audio Field
            image_field_content,  # Image Field
        ],
    )
    my_deck.add_note(note)

# --- Save Package ---
package = genanki.Package(my_deck)
package.media_files = media_files_list
package.write_to_file(OUTPUT_FILENAME)

print(f"\nSuccess! Created '{OUTPUT_FILENAME}' with reverse cards included.")
