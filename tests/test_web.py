from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sound_analyzer.catalog import Catalog
from sound_analyzer.web.server import create_app

CLIPS = [
    ("1001/dog.wav", "animals", "dogs", "dog barking", 1.0),
    ("1001/cat.wav", "animals", "cats", "cat meowing", 2.5),
    ("1002/door.wav", "doors", "metal", "metal door slam", 0.4),
]


def _write_wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(8000 * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"".join(struct.pack("<h", (index % 200) * 100) for index in range(frames)))


@pytest.fixture()
def library(tmp_path: Path) -> Path:
    catalog = Catalog(tmp_path)
    for relpath, category, subcategory, label, seconds in CLIPS:
        path = tmp_path / relpath
        _write_wav(path, seconds)
        file_id, _ = catalog.upsert_file(
            relpath,
            size=path.stat().st_size,
            mtime=path.stat().st_mtime,
            duration=seconds,
            sample_rate=8000,
            channels=1,
            codec="pcm_s16le",
        )
        catalog.replace_clips(file_id, [(0.0, seconds)])
        clip = catalog.clips_for_file(file_id)[0]
        catalog.save_tags(
            clip.id,
            category=category,
            subcategory=subcategory,
            tags=[{"label": label, "score": 0.8, "source": "clap"}],
            suggested_name=f"{subcategory}_{int(seconds * 1000)}ms_{clip.id:06x}.wav",
            confidence=0.8,
        )
    catalog.close()
    return tmp_path


@pytest.fixture()
def client(library: Path) -> TestClient:
    return TestClient(create_app(library))


def test_library_lists_categories_and_folders(client: TestClient):
    body = client.get("/api/library").json()
    assert body["stats"]["clips"] == 3
    assert {item["name"] for item in body["categories"]} == {"animals", "doors"}
    animals = next(item for item in body["categories"] if item["name"] == "animals")
    assert animals["count"] == 2
    assert {item["path"] for item in body["folders"]} == {"1001", "1002"}


def test_browse_filters_by_category_and_folder(client: TestClient):
    assert client.get("/api/browse", params={"category": "animals"}).json()["total"] == 2
    assert client.get("/api/browse", params={"subcategory": "dogs"}).json()["total"] == 1
    assert client.get("/api/browse", params={"folder": "1002"}).json()["total"] == 1
    assert client.get("/api/browse", params={"q": "meow"}).json()["total"] == 1
    assert client.get("/api/browse", params={"max_duration": 0.5}).json()["total"] == 1


def test_browse_paginates_and_sorts(client: TestClient):
    first = client.get("/api/browse", params={"sort": "short", "limit": 1}).json()
    assert first["total"] == 3
    assert len(first["results"]) == 1
    assert first["results"][0]["name"] == "metal"

    second = client.get("/api/browse", params={"sort": "short", "limit": 1, "offset": 1}).json()
    assert second["results"][0]["id"] != first["results"][0]["id"]

    longest = client.get("/api/browse", params={"sort": "long", "limit": 1}).json()
    assert longest["results"][0]["duration"] == pytest.approx(2.5, abs=0.01)


def test_clip_payload_carries_file_metadata(client: TestClient):
    clip_id = client.get("/api/browse", params={"q": "dog"}).json()["results"][0]["id"]
    body = client.get(f"/api/clip/{clip_id}").json()
    assert body["category"] == "animals"
    assert body["tags"][0]["label"] == "dog barking"
    assert body["sample_rate"] == 8000
    assert body["channels"] == 1
    assert body["codec"] == "pcm_s16le"
    assert body["is_full_file"] is True


def test_missing_clip_is_a_404(client: TestClient):
    assert client.get("/api/clip/9999").status_code == 404


def test_audio_is_served_with_range_support(client: TestClient):
    clip_id = client.get("/api/browse").json()["results"][0]["id"]
    response = client.get(f"/api/clip/{clip_id}/audio")
    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"

    partial = client.get(f"/api/clip/{clip_id}/audio", headers={"Range": "bytes=0-63"})
    assert partial.status_code == 206
    assert len(partial.content) == 64


def test_peaks_return_the_requested_resolution(client: TestClient):
    clip_id = client.get("/api/browse").json()["results"][0]["id"]
    body = client.get(f"/api/clip/{clip_id}/peaks", params={"buckets": 32}).json()
    assert len(body["peaks"]) == 32
    assert all(0.0 <= value <= 1.0 for value in body["peaks"])


def test_index_and_static_assets_are_served(client: TestClient):
    assert "sound-analyzer" in client.get("/").text
    assert client.get("/static/css/tokens.css").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200
