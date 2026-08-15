from sound_analyzer.segment import invert_silences, parse_silence_log


def test_parse_silence_log():
    log = """
[silencedetect @ 0x1] silence_start: 0.512
[silencedetect @ 0x1] silence_end: 1.984 | silence_duration: 1.472
[silencedetect @ 0x1] silence_start: 5.0
[silencedetect @ 0x1] silence_end: 5.8 | silence_duration: 0.8
"""
    assert parse_silence_log(log) == [(0.512, 1.984), (5.0, 5.8)]


def test_invert_silences_splits_cd_track():
    silences = [(1.0, 1.5), (3.0, 3.4)]
    regions = invert_silences(silences, duration=5.0, min_clip=0.1, merge_gap=0.05, pad=0.0)
    assert regions[0][0] == 0.0
    assert len(regions) == 3
    assert regions[-1][1] == 5.0


def test_invert_silences_no_silence_keeps_whole_file():
    assert invert_silences([], duration=20.0) == [(0.0, 20.0)]
