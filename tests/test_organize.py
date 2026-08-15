from pathlib import Path

from sound_analyzer.catalog import Catalog, ClipRow
from sound_analyzer.organize import _dest_for_clip, apply_organize, undo_organize


def test_organized_dest_uses_category_tree(tmp_path: Path):
    clip = ClipRow(
        id=10,
        file_id=1,
        relpath="1002/1002_Animals_01.mp3",
        start_sec=0.0,
        end_sec=1.0,
        duration_ms=1000,
        category="animals",
        subcategory="dogs",
        tags_json=None,
        suggested_name="dogs_bark_1000ms_00000a.wav",
        confidence=0.9,
        embedded=1,
        tagged=1,
    )
    dest = _dest_for_clip(tmp_path, clip)
    assert dest.relative_to(tmp_path).as_posix() == "organized/animals/dogs/dogs_bark_1000ms_00000a.wav"


def test_apply_and_undo_copy(tmp_path: Path):
    src_dir = tmp_path / "cd1"
    src_dir.mkdir()
    src = src_dir / "track.wav"
    src.write_bytes(b"RIFF" + b"\x00" * 64)
    catalog = Catalog(tmp_path)
    file_id, _ = catalog.upsert_file(
        "cd1/track.wav",
        size=src.stat().st_size,
        mtime=src.stat().st_mtime,
        duration=1.0,
        sample_rate=44100,
        channels=1,
        codec="pcm_s16le",
    )
    catalog.replace_clips(file_id, [(0.0, 1.0)])
    clip = catalog.clips_for_file(file_id)[0]
    catalog.save_tags(
        clip.id,
        category="animals",
        subcategory="dogs",
        tags=[{"label": "dog barking", "score": 0.9, "source": "clap"}],
        suggested_name="dogs_bark_1000ms_000001.wav",
        confidence=0.9,
    )
    catalog.close()

    stats = apply_organize(tmp_path)
    dest = tmp_path / "organized" / "animals" / "dogs" / "dogs_bark_1000ms_000001.wav"
    assert dest.exists()
    assert src.exists()
    assert stats["hardlink"] + stats["copy"] == 1

    undo = undo_organize(tmp_path)
    assert undo["removed"] == 1
    assert not dest.exists()
    assert src.exists()


def test_organized_dest_uses_category_tree(tmp_path: Path):
    clip = ClipRow(
        id=10,
        file_id=1,
        relpath="1002/1002_Animals_01.mp3",
        start_sec=0.0,
        end_sec=1.0,
        duration_ms=1000,
        category="animals",
        subcategory="dogs",
        tags_json=None,
        suggested_name="dogs_bark_1000ms_00000a.wav",
        confidence=0.9,
        embedded=1,
        tagged=1,
    )
    dest = _dest_for_clip(tmp_path, clip)
    assert dest.relative_to(tmp_path).as_posix() == "organized/animals/dogs/dogs_bark_1000ms_00000a.wav"
