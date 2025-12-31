import flet as ft
import os

try:
    from ankiflow.core import (
        SUBJECT_CATEGORIES,
        SEMANTIC_CATEGORIES,
        fetch_category_words,
        save_words_to_csv,
        create_deck,
    )
except ImportError:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).parent.parent))
    from ankiflow.core import (
        SUBJECT_CATEGORIES,
        SEMANTIC_CATEGORIES,
        fetch_category_words,
        save_words_to_csv,
        create_deck,
    )


def main(page: ft.Page):
    page.title = "AnkiFlow"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20

    # --- STATE ---
    log_messages = ft.Column(scroll=ft.ScrollMode.AUTO, height=200)

    def log(message: str):
        log_messages.controls.append(ft.Text(message))
        page.update()
        log_messages.scroll_to(offset=-1, duration=300)

    # --- TAB 1: DOWNLOAD CONTROLS ---

    type_dropdown = ft.Dropdown(
        label="Category Type",
        options=[
            ft.dropdown.Option("Subject"),
            ft.dropdown.Option("Semantic"),
        ],
        value="Subject",
        width=200,
    )

    category_dropdown = ft.Dropdown(
        label="Select Category",
        width=400,
        options=[
            ft.dropdown.Option(str(i), c.name) for i, c in enumerate(SUBJECT_CATEGORIES)
        ],
        value="0",
    )

    limit_input = ft.TextField(
        label="Limit", value="20", width=100, keyboard_type=ft.KeyboardType.NUMBER
    )

    def on_type_change(e):
        is_subject = type_dropdown.value == "Subject"
        cats = SUBJECT_CATEGORIES if is_subject else SEMANTIC_CATEGORIES
        category_dropdown.options = [
            ft.dropdown.Option(str(i), c.name) for i, c in enumerate(cats)
        ]
        category_dropdown.value = "0"
        page.update()

    type_dropdown.on_change = on_type_change

    def get_collection_files():
        os.makedirs("collections", exist_ok=True)
        files = [f for f in os.listdir("collections") if f.endswith(".csv")]
        return [ft.dropdown.Option(os.path.join("collections", f), f) for f in files]

    input_csv_field = ft.Dropdown(
        label="Select Collection CSV",
        options=get_collection_files(),
        width=400,
    )

    def refresh_collections():
        input_csv_field.options = get_collection_files()
        input_csv_field.update()

    # --- RESULTS TABLE ---
    results_table = ft.DataTable(
        columns=[
            ft.DataColumn(label=ft.Text("English")),
            ft.DataColumn(label=ft.Text("Korean")),
            ft.DataColumn(label=ft.Text("Definition")),
        ],
        rows=[],
        visible=False,
    )

    table_container = ft.Column(
        [results_table],
        scroll=ft.ScrollMode.AUTO,
        height=500,  # Limit height to keep layout clean
        visible=False,
    )

    def download_click(e):
        try:
            limit = int(limit_input.value)
            idx = int(category_dropdown.value)
            is_subject = type_dropdown.value == "Subject"

            log(f"Starting download... (Category: {idx}, Limit: {limit})")

            e.control.disabled = True
            e.control.update()

            # Clear previous results
            results_table.rows.clear()
            results_table.visible = False
            table_container.visible = False
            page.update()

            words = fetch_category_words(
                category_idx=idx, is_subject=is_subject, limit=limit, callback=log
            )

            if words:
                cat_name = (SUBJECT_CATEGORIES if is_subject else SEMANTIC_CATEGORIES)[
                    idx
                ].name
                filename = save_words_to_csv(words, cat_name)
                log(f"Saved to: {filename}")

                # Refresh dropdown and select the new file
                refresh_collections()
                input_csv_field.value = filename
                input_csv_field.update()

                # Populate Table
                for word in words:
                    results_table.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(content=ft.Text(word.get("english", ""))),
                                ft.DataCell(content=ft.Text(word.get("korean", ""))),
                                ft.DataCell(
                                    content=ft.Text(
                                        word.get("definition", "")[:50] + "..."
                                        if len(word.get("definition", "")) > 50
                                        else word.get("definition", "")
                                    )
                                ),
                            ]
                        )
                    )
                results_table.visible = True
                table_container.visible = True
                page.update()
            else:
                log("No words found.")

        except Exception as ex:
            log(f"Error: {ex}")
        finally:
            e.control.disabled = False
            e.control.update()

    download_btn = ft.Button("Download", on_click=download_click)

    download_view = ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "Download Vocabulary from KRDict",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Row([type_dropdown, category_dropdown]),
                limit_input,
                download_btn,
                table_container,
            ],
            spacing=20,
        ),
        padding=20,
    )

    # --- TAB 2: GENERATE CONTROLS ---

    deck_title_field = ft.TextField(
        label="Deck Title", value="My Korean Deck", width=400
    )

    check_eng_kor = ft.Checkbox(label="English -> Korean", value=True)
    check_listening = ft.Checkbox(label="Listening (Audio -> Eng)", value=True)
    check_image = ft.Checkbox(label="Image -> Korean (Requires Download)", value=False)

    def generate_click(e):
        try:
            csv_path = input_csv_field.value
            title = deck_title_field.value
            output = title.replace(" ", "_").lower() + ".apkg"

            if not os.path.exists(csv_path):
                log(f"Error: File not found: {csv_path}")
                return

            log(f"Generating deck '{title}' from '{csv_path}'...")

            e.control.disabled = True
            e.control.update()

            assert csv_path is not None
            create_deck(
                input_csv=csv_path,
                output_file=output,
                deck_title=title,
                include_eng_kor=check_eng_kor.value or True,
                include_listening=check_listening.value or True,
                include_image_card=check_image.value or False,
                callback=log,
            )

            log(f"Done! Deck saved to: {output}")

        except Exception as ex:
            log(f"Error: {ex}")
        finally:
            e.control.disabled = False
            e.control.update()

    generate_btn = ft.Button("Generate Deck", on_click=generate_click)

    generate_view = ft.Container(
        content=ft.Column(
            [
                ft.Text("Generate Anki Deck", size=20, weight=ft.FontWeight.BOLD),
                input_csv_field,
                deck_title_field,
                ft.Text("Card Types:", weight=ft.FontWeight.BOLD),
                check_eng_kor,
                check_listening,
                check_image,
                generate_btn,
            ],
            spacing=10,
        ),
        padding=20,
    )

    # --- TABS LAYOUT (Flet 0.80.0+ Style) ---

    tabs_control = ft.Tabs(
        selected_index=0,
        length=2,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(
                            label="Download Collection", icon=ft.Icons.FILE_DOWNLOAD
                        ),
                        ft.Tab(label="Generate Deck", icon=ft.Icons.EDIT),
                    ]
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        download_view,
                        generate_view,
                    ],
                ),
            ],
        ),
    )

    page.add(
        tabs_control,
        ft.Divider(),
        ft.Text("Log Output:", weight=ft.FontWeight.BOLD),
        ft.Container(
            content=log_messages,
            bgcolor="grey100",
            padding=10,
            border_radius=5,
            border=ft.Border.all(1, "grey400"),
            height=200,
        ),
    )


if __name__ == "__main__":
    ft.run(main=main)
