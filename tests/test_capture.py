"""Source detection for the unified capture box."""

import pytest

from app.ingest.capture import detect_source


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://example.com/article", "link"),
        ("example.com/post", "link"),
        ("www.example.com", "link"),
        # A note that merely contains a link is still a note -- fetching the
        # article would throw away what the user actually wrote.
        ("check out https://x.com, looks useful", "text"),
        ("remind me to call mum", "text"),
        ("Bought milk. Cost 3.50.", "text"),
        ("   ", "empty"),
        ("", "empty"),
    ],
)
def test_text_detection(text, expected):
    assert detect_source(text=text) == expected


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("shot.PNG", "image"),
        ("a.jpg", "image"),
        ("memo.m4a", "voice"),
        ("recording.webm", "voice"),
        ("doc.pdf", "file"),
        ("cv.docx", "file"),
        ("notes.md", "file"),
    ],
)
def test_extension_detection(filename, expected):
    assert detect_source(filename=filename) == expected


@pytest.mark.parametrize(
    "filename,content_type,expected",
    [
        # A pasted screenshot arrives with no useful filename.
        ("blob", "image/png", "image"),
        ("", "audio/webm", "voice"),
        ("x.bin", "application/pdf", "file"),
    ],
)
def test_falls_back_to_mime_type(filename, content_type, expected):
    assert detect_source(filename=filename, content_type=content_type) == expected


def test_a_file_wins_over_accompanying_text():
    assert detect_source(text="here's the receipt", filename="r.png") == "image"
