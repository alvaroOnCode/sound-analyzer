from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# English phrases that CLAP understands, mapped to a folder tree + Spanish aliases.


@dataclass(frozen=True)
class Label:
    prompt: str
    category: str
    subcategory: str
    aliases: tuple[str, ...] = ()


LABELS: tuple[Label, ...] = (
    Label("dog barking", "animals", "dogs", ("perro", "ladrido", "can")),
    Label("cat meowing", "animals", "cats", ("gato", "maullido")),
    Label("bird chirping", "animals", "birds", ("pajaro", "pájaro", "ave", "canto")),
    Label("horse neighing", "animals", "horses", ("caballo", "relincho")),
    Label("cow mooing", "animals", "livestock", ("vaca", "mugido")),
    Label("insect buzzing", "animals", "insects", ("insecto", "mosca", "abeja")),
    Label("wolf howling", "animals", "wild", ("lobo", "aullido")),
    Label("lion roar", "animals", "wild", ("leon", "león", "rugido")),
    Label("crowd of animals", "animals", "generic", ("animales", "fauna")),
    Label("metal door slam", "doors", "metal", ("puerta metal", "portazo metal")),
    Label("wooden door closing", "doors", "wood", ("puerta madera", "portazo")),
    Label("door creak", "doors", "creak", ("bisagra", "chirrido puerta", "crujido puerta")),
    Label("door knock", "doors", "knock", ("llamada puerta", "golpes puerta")),
    Label("glass breaking", "impacts", "glass", ("cristal", "vidrio", "rotura")),
    Label("metal impact hit", "impacts", "metal", ("golpe metal", "hierro")),
    Label("wood impact hit", "impacts", "wood", ("golpe madera", "madera")),
    Label("punch impact", "impacts", "body", ("puñetazo", "golpe cuerpo")),
    Label("whoosh pass by", "whoosh", "generic", ("whoosh", "pasada", "barrido")),
    Label("fast whoosh", "whoosh", "fast", ("ráfaga", "swipe")),
    Label("cinematic whoosh", "whoosh", "cinematic", ("transición",)),
    Label("explosion boom", "weapons", "explosion", ("explosion", "explosión", "bomba")),
    Label("gunshot", "weapons", "guns", ("disparo", "pistola", "rifle")),
    Label("reload gun", "weapons", "guns", ("recarga",)),
    Label("sword clash", "weapons", "melee", ("espada", "choque")),
    Label("car engine", "vehicles", "cars", ("coche", "motor", "auto")),
    Label("car horn", "vehicles", "cars", ("claxon", "bocina")),
    Label("car crash", "vehicles", "crash", ("choque coche", "accidente")),
    Label("train passing", "vehicles", "train", ("tren",)),
    Label("airplane flyby", "vehicles", "air", ("avion", "avión", "helicoptero", "helicóptero")),
    Label("motorcycle", "vehicles", "bikes", ("moto", "motocicleta")),
    Label("rain ambience", "ambience", "rain", ("lluvia",)),
    Label("thunder storm", "ambience", "storm", ("trueno", "tormenta")),
    Label("wind ambience", "ambience", "wind", ("viento",)),
    Label("ocean waves", "ambience", "water", ("mar", "olas", "playa")),
    Label("forest ambience", "ambience", "nature", ("bosque", "selva")),
    Label("city traffic ambience", "ambience", "city", ("ciudad", "trafico", "tráfico")),
    Label("crowd murmur", "ambience", "crowd", ("multitud", "gente", "murmullo")),
    Label("fire crackling", "ambience", "fire", ("fuego", "hoguera", "llama")),
    Label("underwater ambience", "ambience", "water", ("bajo el agua", "submarino")),
    Label("footsteps on wood", "foley", "footsteps", ("pasos", "pisadas")),
    Label("footsteps on gravel", "foley", "footsteps", ("pasos grava",)),
    Label("cloth rustle", "foley", "fabric", ("tela", "ropa")),
    Label("paper rustle", "foley", "paper", ("papel",)),
    Label("keys jingle", "foley", "keys", ("llaves",)),
    Label("coins dropping", "foley", "coins", ("monedas",)),
    Label("water splash", "foley", "water", ("salpicadura", "chapoteo")),
    Label("user interface click", "ui", "click", ("click", "clic", "boton", "botón")),
    Label("notification beep", "ui", "beep", ("beep", "aviso", "pitido")),
    Label("sci-fi beep", "scifi", "beep", ("ciencia ficción", "laser", "láser")),
    Label("spaceship hum", "scifi", "space", ("nave", "espacio")),
    Label("robot servo", "scifi", "robot", ("robot",)),
    Label("telephone ring", "mechanical", "phone", ("telefono", "teléfono", "timbre")),
    Label("alarm bell", "mechanical", "alarm", ("alarma", "sirena")),
    Label("clock ticking", "mechanical", "clock", ("reloj", "tic")),
    Label("machine motor", "mechanical", "machine", ("maquina", "máquina", "engranaje")),
    Label("speech talking", "speech", "talk", ("voz", "habla", "dialogo", "diálogo")),
    Label("crowd cheer", "human", "crowd", ("ovacion", "ovación", "aplausos")),
    Label("laughter", "human", "laugh", ("risa",)),
    Label("scream", "human", "scream", ("grito",)),
    Label("cough", "human", "body", ("tos",)),
    Label("cartoon boing", "cartoon", "boing", ("boing", "muelle", "cartoon")),
    Label("music sting", "music", "sting", ("musica", "música", "sting")),
    Label("drum hit", "music", "percussion", ("tambor", "percusión")),
)

SPANISH_QUERY_MAP: dict[str, str] = {}
for _label in LABELS:
    for alias in _label.aliases:
        SPANISH_QUERY_MAP[alias.lower()] = _label.prompt
SPANISH_QUERY_MAP.update(
    {
        "puerta": "door",
        "golpe": "impact hit",
        "metal": "metal",
        "madera": "wood",
        "perro": "dog bark",
        "gato": "cat",
        "pajaro": "bird",
        "pájaro": "bird",
        "lluvia": "rain",
        "viento": "wind",
        "fuego": "fire",
        "coche": "car",
        "disparo": "gunshot",
        "explosion": "explosion",
        "explosión": "explosion",
        "pasos": "footsteps",
        "whoosh": "whoosh",
        "ambiente": "ambience",
        "ciudad": "city ambience",
        "bosque": "forest",
        "mar": "ocean waves",
        "trueno": "thunder",
        "alarma": "alarm",
        "voz": "speech",
        "grito": "scream",
        "risa": "laughter",
    }
)


def expand_query(text: str) -> str:
    """Append English equivalents so CLAP can match Spanish queries."""
    lowered = text.lower()
    extras: list[str] = []
    for alias, english in sorted(SPANISH_QUERY_MAP.items(), key=lambda kv: -len(kv[0])):
        if alias in lowered and english.lower() not in lowered:
            extras.append(english)
    if not extras:
        return text
    return f"{text}, " + ", ".join(dict.fromkeys(extras))


def slugify(text: str, *, max_len: int = 48) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    ascii_text = re.sub(r"_+", "_", ascii_text)
    return ascii_text[:max_len] or "sfx"


def suggested_filename(
    *,
    subcategory: str,
    extra_tag: str | None,
    duration_ms: int,
    clip_id: int,
    ext: str = ".wav",
) -> str:
    parts = [slugify(subcategory)]
    if extra_tag:
        extra = slugify(extra_tag)
        if extra and extra not in parts[0]:
            parts.append(extra)
    stem = "_".join(parts)
    return f"{stem}_{duration_ms}ms_{clip_id:06x}{ext}"


def prompts() -> list[str]:
    return [label.prompt for label in LABELS]


def label_by_prompt(prompt: str) -> Label | None:
    for label in LABELS:
        if label.prompt == prompt:
            return label
    return None
