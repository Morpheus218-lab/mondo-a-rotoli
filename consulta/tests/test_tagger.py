# consulta/tests/test_tagger.py
import json

import requests

import tagger


class _RispostaFinta:
    def __init__(self, corpo_json):
        self._corpo_json = corpo_json

    def raise_for_status(self):
        pass

    def json(self):
        return self._corpo_json


def test_genera_tag_ritorna_la_lista_di_tag_dalla_risposta_di_ollama(monkeypatch):
    corpo = {"response": json.dumps({"tags": ["saluti", "amicizia"]})}
    monkeypatch.setattr(tagger.requests, "post", lambda *a, **k: _RispostaFinta(corpo))

    tag = tagger.genera_tag("ciao a tutti", "http://localhost:11434", "llama3.1:8b")

    assert tag == ["saluti", "amicizia"]


def test_genera_tag_ritorna_none_se_meno_di_due_tag(monkeypatch):
    corpo = {"response": json.dumps({"tags": ["saluti"]})}
    monkeypatch.setattr(tagger.requests, "post", lambda *a, **k: _RispostaFinta(corpo))

    assert tagger.genera_tag("ciao", "http://localhost:11434", "llama3.1:8b") is None


def test_genera_tag_ritorna_none_se_la_risposta_non_e_json_valido(monkeypatch):
    corpo = {"response": "non e' json"}
    monkeypatch.setattr(tagger.requests, "post", lambda *a, **k: _RispostaFinta(corpo))

    assert tagger.genera_tag("ciao", "http://localhost:11434", "llama3.1:8b") is None


def test_genera_tag_ignora_tag_vuoti_o_non_stringa(monkeypatch):
    corpo = {"response": json.dumps({"tags": ["saluti", "", "  ", "amicizia", 42]})}
    monkeypatch.setattr(tagger.requests, "post", lambda *a, **k: _RispostaFinta(corpo))

    tag = tagger.genera_tag("ciao", "http://localhost:11434", "llama3.1:8b")

    assert tag == ["saluti", "amicizia"]


def test_genera_tag_ritorna_none_se_ollama_non_risponde(monkeypatch):
    def richiesta_rotta(*a, **k):
        raise requests.exceptions.ConnectionError("ollama non disponibile")

    monkeypatch.setattr(tagger.requests, "post", richiesta_rotta)

    assert tagger.genera_tag("ciao", "http://localhost:11434", "llama3.1:8b") is None
