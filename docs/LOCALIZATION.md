# App language

Z8 starts in **English**, including on devices whose system language is Korean.
Choose **Settings → App language → 한국어** to use Korean, or **설정 → 앱 언어 → English** to switch back.
The choice is saved in app-private settings. A failed save leaves the previous language selected.

Changing the app language recreates open app screens when they return to the foreground.
It does not delete projects or credentials, stop the terminal service, or rerun CLI commands.
Project names, paths, terminal output, draft text and other user content are preserved.
Messages already recorded by a running operation or in notification history retain the language used when they were created.

New terminal sessions pass the choice to Z8's own CLI notices using `Z8_UI_LANGUAGE`.
Existing sessions keep their original process environment. Open a new terminal to change the language of Z8's Codex local-mode prompt.
The language of external CLIs, websites and the device browser is controlled by those tools and services.

## Contributions

App-owned Java labels use `Z8Text.text("English", "한국어")` and are evaluated when displayed.
Do not localize commands, protocol keys, identifiers, paths or persisted user input.
Avoid caching translated labels in static fields; use a method when a value must follow the current language.
Keep both translations equally precise for consent, deletion, data handling and execution boundaries.

`Z8Language` persists the choice, wraps Android contexts and refreshes screens after a change.
The preparer applies the locale to the terminal, Z8 screens and auxiliary upstream screens.
The default website and README are English; explicit Korean links remain available without browser-language redirects.

Run `python3 -m unittest discover -s tests -p test_language.py -v` for preference, persistence and lifecycle behavior.
Run `python3 -m unittest discover -s tests -p test_codex_launch.py -v` for both consent languages and unchanged launch boundaries.
