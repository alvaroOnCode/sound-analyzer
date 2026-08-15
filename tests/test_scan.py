from pathlib import Path

from sound_analyzer.catalog import Catalog
from sound_analyzer.scan import iter_audio_files


def test_iter_audio_skips_index_and_organized(tmp_path: Path):
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "hit.wav").write_bytes(b"RIFF")
    (tmp_path / ".sound-analyzer").mkdir()
    (tmp_path / ".sound-analyzer" / "nope.wav").write_bytes(b"RIFF")
    (tmp_path / "organized" / "animals").mkdir(parents=True)
    (tmp_path / "organized" / "animals" / "copy.wav").write_bytes(b"RIFF")
    files = [p.relative_to(tmp_path).as_posix() for p in iter_audio_files(tmp_path)]
    assert files == ["keep/hit.wav"]


def test_catalog_roundtrip(tmp_path: Path):
    catalog = Catalog(tmp_path)
    file_id, changed = catalog.upsert_file(
        "cd1/track.wav",
        size=10,
        mtime=1.0,
        duration=2.5,
        sample_rate=44100,
        channels=2,
        codec="pcm_s16le",
    )
    assert changed
    catalog.replace_clips(file_id, [(0.0, 1.0), (1.2, 2.5)])
    clips = catalog.clips_for_file(file_id)
    assert len(clips) == 2
    assert catalog.stats()["clips"] == 2
    catalog.close()
    assert (tmp_path / ".sound-analyzer" / "catalog.sqlite").exists()
