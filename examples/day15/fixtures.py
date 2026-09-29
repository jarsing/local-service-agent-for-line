"""Fixed, synthetic five-question development fixture; not real user dialogue."""
from .session_budget import MODEL_ID, SafeTurn

FIXTURE_ENVELOPE = {
    "model": "models/" + MODEL_ID,
    "systemInstruction": {"parts": [{
        "text": "LOCAL synthetic contract: current request wins; backend owns consent."
    }]},
    "tools": [{"functionDeclarations": [{
        "name": "search_local_places",
        "description": "Synthetic abbreviated schema, not the SDK wire schema.",
        "parameters": {"type": "OBJECT", "properties": {
            "area": {"type": "STRING"}, "dietary_type": {"type": "STRING"}
        }},
    }]}],
}

QUESTIONS = (
    "今天想吃素，花壇有什麼吃的？",
    "查花壇的活動。",
    "停車資料有嗎？",
    "那公車時間呢？",
    "剛才那個鄉鎮，再找一家吃的。",
)
PROJECTIONS = (
    SafeTurn("places", "花壇鄉"),
    SafeTurn("events", "花壇鄉"),
    SafeTurn("help"),
    SafeTurn("help"),
    SafeTurn("places", "花壇鄉"),
)
