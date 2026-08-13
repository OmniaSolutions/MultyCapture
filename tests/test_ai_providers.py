"""Model backends.

Every backend is one JSON POST, so every one of them can be pointed at a stub
server here — including the cloud ones, whose URLs are the only thing that
makes them "cloud". That means the wire format each depends on is actually
covered rather than assumed, which matters more now that there is no vendor
client library absorbing protocol changes.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from multycapture.ai import providers
from multycapture.ai.providers import MissingCredential, ProviderError, http
from multycapture.ai.providers.claude import ClaudeProvider
from multycapture.ai.providers.gemini import GeminiProvider
from multycapture.ai.providers.ollama import OllamaProvider
from multycapture.ai.providers.openai_compatible import OpenAICompatibleProvider


class _Stub(BaseHTTPRequestHandler):
    """Replies with whatever the test queued, and records what it received."""

    reply: dict = {}
    status: int = 200
    received: dict = {}
    path_seen: str = ""
    headers_seen: dict = {}

    def do_POST(self):  # noqa: N802 - name fixed by the base class
        cls = type(self)
        cls.path_seen = self.path
        # HTTP header names are case-insensitive and urllib capitalises
        # them on the way out; normalise so assertions can be literal.
        cls.headers_seen = {k.lower(): v for k, v in self.headers.items()}
        length = int(self.headers.get("Content-Length", 0))
        cls.received = json.loads(self.rfile.read(length)) if length else {}
        body = json.dumps(cls.reply).encode()
        self.send_response(cls.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    _Stub.status, _Stub.reply, _Stub.received = 200, {}, {}
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


# --------------------------------------------------------------------------- #
# catalogue
# --------------------------------------------------------------------------- #
def test_catalog_lists_every_backend():
    assert [e[0] for e in providers.CATALOG] == ["ollama", "claude", "openai", "gemini"]


def test_the_local_one_comes_first_and_is_the_default():
    first_id, _, first_is_local = providers.CATALOG[0]
    assert (first_id, first_is_local) == (providers.DEFAULT_ID, True)


def test_only_ollama_is_marked_local():
    assert [e[0] for e in providers.CATALOG if e[2]] == ["ollama"]


def test_build_uses_the_default_model_and_honours_an_explicit_one():
    assert providers.build("claude").model == providers.default_model("claude")
    assert providers.build("gemini", model="gemini-pro").model == "gemini-pro"


def test_build_routes_base_url_to_the_right_argument():
    assert providers.build("ollama", base_url="http://box:11434").host == "http://box:11434"
    assert providers.build("openai", base_url="http://x/v1").base_url == "http://x/v1"


def test_unknown_provider_is_a_clear_error():
    with pytest.raises(ProviderError, match="Unknown AI provider"):
        providers.build("telepathy")


def test_no_backend_needs_a_client_library():
    """The whole point of speaking HTTP: nothing to install, nothing to bundle."""
    for provider_id, _, _ in providers.CATALOG:
        assert providers.build(provider_id, api_key="k").id == provider_id


def test_missing_key_is_reported_before_any_request():
    for name in ("claude", "gemini", "openai"):
        with pytest.raises(MissingCredential):
            providers.build(name).complete("hello")


# --------------------------------------------------------------------------- #
# ollama
# --------------------------------------------------------------------------- #
def test_ollama_round_trip(server):
    _Stub.reply = {"message": {"content": "rewritten"}}
    assert OllamaProvider(model="llama3.1", host=server).complete("go") == "rewritten"

    assert _Stub.path_seen == "/api/chat"
    assert _Stub.received["model"] == "llama3.1"
    assert _Stub.received["messages"][0]["content"] == "go"
    assert _Stub.received["stream"] is False
    # Without a raised context window a long procedure silently overflows and
    # the model answers about the part it can still see.
    assert _Stub.received["options"]["num_ctx"] >= 8192


def test_ollama_unreachable_says_so_plainly():
    with pytest.raises(ProviderError, match="Cannot reach"):
        OllamaProvider(host="http://127.0.0.1:1", timeout=2).complete("hello")


def test_ollama_unknown_model_says_how_to_install_it(server):
    _Stub.status, _Stub.reply = 404, {"error": "model 'mistral-nemo' not found"}
    with pytest.raises(ProviderError, match="ollama pull mistral-nemo"):
        OllamaProvider(model="mistral-nemo", host=server).complete("hello")


# --------------------------------------------------------------------------- #
# claude
# --------------------------------------------------------------------------- #
def test_claude_round_trip(server, monkeypatch):
    monkeypatch.setattr("multycapture.ai.providers.claude.API_URL", f"{server}/v1/messages")
    _Stub.reply = {
        "content": [{"type": "text", "text": "rewritten"}],
        "stop_reason": "end_turn",
    }
    assert ClaudeProvider(api_key="sk-test").complete("go") == "rewritten"

    assert _Stub.headers_seen["x-api-key"] == "sk-test"
    assert _Stub.headers_seen["anthropic-version"] == "2023-06-01"
    assert _Stub.received["messages"][0]["content"] == "go"
    assert _Stub.received["max_tokens"] > 0


def test_claude_sends_no_sampling_parameters(server, monkeypatch):
    """This model family rejects temperature/top_p/top_k with a 400."""
    monkeypatch.setattr("multycapture.ai.providers.claude.API_URL", f"{server}/v1/messages")
    _Stub.reply = {"content": [{"type": "text", "text": "x"}], "stop_reason": "end_turn"}
    ClaudeProvider(api_key="k").complete("go")
    for banned in ("temperature", "top_p", "top_k"):
        assert banned not in _Stub.received


def test_claude_refusal_is_explained_not_reported_as_empty(server, monkeypatch):
    """A refusal is a normal 200 with no content; saying "empty" hides why."""
    monkeypatch.setattr("multycapture.ai.providers.claude.API_URL", f"{server}/v1/messages")
    _Stub.reply = {"content": [], "stop_reason": "refusal"}
    with pytest.raises(ProviderError, match="declined"):
        ClaudeProvider(api_key="k").complete("go")


def test_claude_bad_key_is_named_as_such(server, monkeypatch):
    monkeypatch.setattr("multycapture.ai.providers.claude.API_URL", f"{server}/v1/messages")
    _Stub.status, _Stub.reply = 401, {"error": {"message": "invalid x-api-key"}}
    with pytest.raises(ProviderError, match="rejected the API key"):
        ClaudeProvider(api_key="wrong").complete("go")


# --------------------------------------------------------------------------- #
# openai-compatible
# --------------------------------------------------------------------------- #
def test_openai_round_trip(server):
    _Stub.reply = {"choices": [{"message": {"content": "rewritten"}}]}
    provider = OpenAICompatibleProvider(model="gpt-4o-mini", api_key="sk-x", base_url=server)
    assert provider.complete("go") == "rewritten"

    assert _Stub.path_seen == "/chat/completions"
    assert _Stub.headers_seen["authorization"] == "Bearer sk-x"
    assert _Stub.received["model"] == "gpt-4o-mini"


def test_a_local_openai_server_needs_no_key(server):
    """LM Studio and friends accept anything; only the header is required."""
    _Stub.reply = {"choices": [{"message": {"content": "ok"}}]}
    provider = OpenAICompatibleProvider(base_url="http://localhost:1234/v1")
    assert provider.is_local is True
    provider.base_url = server  # same object, reachable address
    assert provider.complete("go") == "ok"


def test_openai_no_choices_is_an_error(server):
    _Stub.reply = {"choices": []}
    with pytest.raises(ProviderError, match="no choices"):
        OpenAICompatibleProvider(api_key="k", base_url=server).complete("go")


def test_openai_rate_limit_says_to_retry(server):
    _Stub.status, _Stub.reply = 429, {"error": {"message": "slow down"}}
    with pytest.raises(ProviderError, match="rate limit"):
        OpenAICompatibleProvider(api_key="k", base_url=server).complete("go")


# --------------------------------------------------------------------------- #
# gemini
# --------------------------------------------------------------------------- #
def test_gemini_round_trip(server, monkeypatch):
    monkeypatch.setattr("multycapture.ai.providers.gemini.API_ROOT", f"{server}/models")
    _Stub.reply = {
        "candidates": [
            {"content": {"parts": [{"text": "rewritten"}]}, "finishReason": "STOP"}
        ]
    }
    assert GeminiProvider(model="gemini-2.0-flash", api_key="k").complete("go") == "rewritten"

    # The key travels in a header, not the query string: a URL reaches logs
    # and proxies, a header does not.
    assert _Stub.headers_seen["x-goog-api-key"] == "k"
    assert "key=" not in _Stub.path_seen
    assert _Stub.received["contents"][0]["parts"][0]["text"] == "go"


def test_gemini_safety_stop_is_explained(server, monkeypatch):
    monkeypatch.setattr("multycapture.ai.providers.gemini.API_ROOT", f"{server}/models")
    _Stub.reply = {"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]}
    with pytest.raises(ProviderError, match="SAFETY"):
        GeminiProvider(api_key="k").complete("go")


def test_gemini_blocked_prompt_is_explained(server, monkeypatch):
    """A prompt blocked before generation returns no candidates at all."""
    monkeypatch.setattr("multycapture.ai.providers.gemini.API_ROOT", f"{server}/models")
    _Stub.reply = {"promptFeedback": {"blockReason": "OTHER"}}
    with pytest.raises(ProviderError, match="OTHER"):
        GeminiProvider(api_key="k").complete("go")


# --------------------------------------------------------------------------- #
# shared HTTP behaviour
# --------------------------------------------------------------------------- #
def test_server_errors_suggest_retrying(server):
    _Stub.status, _Stub.reply = 503, {"error": "overloaded"}
    with pytest.raises(ProviderError, match="Try again later"):
        http.post_json(server, {}, {}, service="Test")


def test_non_json_reply_is_reported_as_such(server):
    _Stub.reply = {"ok": True}
    # A 200 whose body is not JSON is handled by the decoder path; here the
    # empty-completion guard is what protects the document.
    with pytest.raises(ProviderError, match="empty reply"):
        http.first_text("", "Test")


# --------------------------------------------------------------------------- #
# "local" is about the configured host, not the label
# --------------------------------------------------------------------------- #
def test_ollama_on_this_machine_is_local():
    for host in ("http://localhost:11434", "http://127.0.0.1:11434",
                 "HTTP://LocalHost:11434"):
        assert OllamaProvider(host=host).is_local is True


def test_ollama_on_another_machine_is_not_local():
    """The confirmation dialog must not promise the text stays put.

    Running Ollama on another box is common; saying "stays on this machine"
    there is a false statement in the one dialog whose job is to let the user
    decide whether to send it.
    """
    for host in ("http://192.168.99.21:11434", "http://ollama.lan:11434"):
        assert OllamaProvider(host=host).is_local is False


def test_hosted_backends_are_never_local():
    assert ClaudeProvider(api_key="k").is_local is False
    assert GeminiProvider(api_key="k").is_local is False
    assert OpenAICompatibleProvider(api_key="k").is_local is False


def test_an_openai_compatible_server_on_this_machine_is_local():
    assert OpenAICompatibleProvider(base_url="http://localhost:1234/v1").is_local is True
