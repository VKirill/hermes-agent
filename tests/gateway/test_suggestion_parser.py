"""Tests for gateway/suggestion_parser.py."""

from gateway.suggestion_parser import Suggestion, extract_suggestion


class TestExtractSuggestion:
    def test_no_marker_returns_original_text(self):
        text = "Here is a plain response with no suggestion block."
        main, suggestion = extract_suggestion(text)
        assert main == text
        assert suggestion is None

    def test_extracts_next_and_reason(self):
        text = 'Main response text.\n\nSUGGESTION:{"next": "Email Albert Shin", "reason": "CO expires Jul 15", "can_do": true}\n'
        main, suggestion = extract_suggestion(text)
        assert main == "Main response text."
        assert suggestion.next == "Email Albert Shin"
        assert suggestion.reason == "CO expires Jul 15"
        assert suggestion.can_do is True

    def test_extracts_learn(self):
        text = 'Main response text.\n\nSUGGESTION:{"learn": "Used wiki_search to find the event page."}\n'
        main, suggestion = extract_suggestion(text)
        assert main == "Main response text."
        assert suggestion.learn == "Used wiki_search to find the event page."
        assert suggestion.can_do is False

    def test_can_do_defaults_to_false(self):
        text = 'Main response text.\n\nSUGGESTION:{"next": "Call the venue"}\n'
        _, suggestion = extract_suggestion(text)
        assert suggestion.can_do is False

    def test_empty_next_and_learn_returns_none(self):
        text = 'Main response text.\n\nSUGGESTION:{"reason": "Because"}\n'
        main, suggestion = extract_suggestion(text)
        assert main == text
        assert suggestion is None

    def test_invalid_json_returns_original(self):
        text = "Main response text.\n\nSUGGESTION:{not valid json}\n"
        main, suggestion = extract_suggestion(text)
        assert main == text
        assert suggestion is None

    def test_marker_at_end_is_stripped(self):
        text = 'Start.\n\nSUGGESTION:{"next": "X"}\n'
        main, suggestion = extract_suggestion(text)
        assert main == "Start."
        assert suggestion.next == "X"

    def test_marker_not_at_end_is_ignored(self):
        text = 'Start.\nSUGGESTION:{"next": "X"}\nEnd.'
        main, suggestion = extract_suggestion(text)
        assert main == text
        assert suggestion is None

    def test_empty_response_returns_none(self):
        main, suggestion = extract_suggestion("")
        assert main == ""
        assert suggestion is None

    def test_whitespace_only_response_returns_none(self):
        main, suggestion = extract_suggestion("   \n  ")
        assert suggestion is None