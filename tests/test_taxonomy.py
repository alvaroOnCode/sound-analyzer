from sound_analyzer.taxonomy import expand_query, slugify, suggested_filename


def test_expand_query_adds_english():
    expanded = expand_query("puerta de metal")
    assert "door" in expanded.lower()
    assert "metal" in expanded.lower()


def test_expand_query_keeps_english():
    assert expand_query("dog bark") == "dog bark"


def test_slugify_and_filename():
    assert slugify("Dog Barking!!") == "dog_barking"
    name = suggested_filename(
        subcategory="dogs",
        extra_tag="dog barking",
        duration_ms=812,
        clip_id=0xA3F91C,
        ext=".wav",
    )
    assert name.startswith("dogs_")
    assert name.endswith("812ms_a3f91c.wav")
