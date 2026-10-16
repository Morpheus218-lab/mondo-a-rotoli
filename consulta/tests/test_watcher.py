# consulta/tests/test_watcher.py
import json

import watcher


def test_pubblica_se_in_programma_non_fa_nulla_senza_remote_url(tmp_path):
    chiamate = []
    risultato = watcher._pubblica_se_in_programma(
        str(tmp_path / "Consulta.md"), None, str(tmp_path / "clone"), "main", 0, 10
    )
    assert risultato == 0
    assert chiamate == []


def test_pubblica_se_in_programma_aspetta_l_intervallo(monkeypatch, tmp_path):
    chiamate = []
    monkeypatch.setattr(watcher.git_publisher, "assicura_clone", lambda *a, **k: chiamate.append("clone"))
    monkeypatch.setattr(watcher.git_publisher, "pubblica", lambda *a, **k: chiamate.append("pubblica") or False)
    monkeypatch.setattr(watcher.time, "time", lambda: 100)

    risultato = watcher._pubblica_se_in_programma(
        str(tmp_path / "Consulta.md"), "git@esempio:remoto.git", str(tmp_path / "clone"), "main",
        ultimo_push=95, intervallo=10,
    )

    assert risultato == 95  # non ancora passato l'intervallo
    assert chiamate == []


def test_pubblica_se_in_programma_pubblica_quando_e_ora(monkeypatch, tmp_path):
    chiamate = []
    monkeypatch.setattr(watcher.git_publisher, "assicura_clone", lambda *a, **k: chiamate.append("clone"))
    monkeypatch.setattr(watcher.git_publisher, "pubblica", lambda *a, **k: chiamate.append("pubblica") or True)
    monkeypatch.setattr(watcher.time, "time", lambda: 200)

    risultato = watcher._pubblica_se_in_programma(
        str(tmp_path / "Consulta.md"), "git@esempio:remoto.git", str(tmp_path / "clone"), "main",
        ultimo_push=95, intervallo=10,
    )

    assert risultato == 200
    assert chiamate == ["clone", "pubblica"]


def test_pubblica_se_in_programma_aggiorna_ultimo_push_anche_se_fallisce(monkeypatch, tmp_path):
    def pubblicazione_rotta(*a, **k):
        raise RuntimeError("push fallito")

    monkeypatch.setattr(watcher.git_publisher, "assicura_clone", lambda *a, **k: None)
    monkeypatch.setattr(watcher.git_publisher, "pubblica", pubblicazione_rotta)
    monkeypatch.setattr(watcher.time, "time", lambda: 200)

    risultato = watcher._pubblica_se_in_programma(
        str(tmp_path / "Consulta.md"), "git@esempio:remoto.git", str(tmp_path / "clone"), "main",
        ultimo_push=95, intervallo=10,
    )

    assert risultato == 200  # non deve sollevare, e non deve ritentare subito al prossimo giro


def test_primo_avvio_tagga_e_scrive_anche_il_backlog_esistente(tmp_path, monkeypatch):
    stato_path = tmp_path / "taggati.jsonl"
    consulta_path = tmp_path / "Consulta.md"
    storico = [{"id": 2, "text": "secondo"}, {"id": 1, "text": "primo"}]  # piu' recente prima
    monkeypatch.setattr(watcher.api_client, "recupera_storico", lambda *a, **k: storico)
    monkeypatch.setattr(watcher.tagger, "genera_tag", lambda testo, host, modello: ["a", "b"])

    watcher.process_one_ciclo("http://esempio", str(stato_path), str(consulta_path), "http://ollama", "modello")

    contenuto = consulta_path.read_text(encoding="utf-8")
    assert contenuto.index("secondo") < contenuto.index("primo")  # id 2 (piu' recente) in cima
    righe_stato = [json.loads(r) for r in stato_path.read_text(encoding="utf-8").splitlines() if r]
    assert {r["id"] for r in righe_stato} == {1, 2}


def test_tagga_solo_i_messaggi_nuovi_rispetto_allo_stato(tmp_path, monkeypatch):
    stato_path = tmp_path / "taggati.jsonl"
    stato_path.write_text(json.dumps({"id": 1, "text": "primo"}) + "\n", encoding="utf-8")
    consulta_path = tmp_path / "Consulta.md"
    storico = [{"id": 2, "text": "secondo"}, {"id": 1, "text": "primo"}]
    monkeypatch.setattr(watcher.api_client, "recupera_storico", lambda *a, **k: storico)

    chiamate = []
    monkeypatch.setattr(
        watcher.tagger,
        "genera_tag",
        lambda testo, host, modello: chiamate.append(testo) or ["a", "b"],
    )

    watcher.process_one_ciclo("http://esempio", str(stato_path), str(consulta_path), "http://ollama", "modello")

    assert chiamate == ["secondo"]


def test_non_registra_il_messaggio_se_la_generazione_tag_fallisce(tmp_path, monkeypatch):
    stato_path = tmp_path / "taggati.jsonl"
    consulta_path = tmp_path / "Consulta.md"
    storico = [{"id": 1, "text": "primo"}]
    monkeypatch.setattr(watcher.api_client, "recupera_storico", lambda *a, **k: storico)
    monkeypatch.setattr(watcher.tagger, "genera_tag", lambda testo, host, modello: None)

    watcher.process_one_ciclo("http://esempio", str(stato_path), str(consulta_path), "http://ollama", "modello")

    assert not stato_path.exists()
    assert not consulta_path.exists()


def test_un_fallimento_blocca_i_messaggi_successivi_dello_stesso_ciclo(tmp_path, monkeypatch):
    stato_path = tmp_path / "taggati.jsonl"
    consulta_path = tmp_path / "Consulta.md"
    storico = [{"id": 2, "text": "secondo"}, {"id": 1, "text": "primo"}]
    monkeypatch.setattr(watcher.api_client, "recupera_storico", lambda *a, **k: storico)

    def genera_tag_fallisce_sul_primo(testo, host, modello):
        return None if testo == "primo" else ["a", "b"]

    monkeypatch.setattr(watcher.tagger, "genera_tag", genera_tag_fallisce_sul_primo)

    watcher.process_one_ciclo("http://esempio", str(stato_path), str(consulta_path), "http://ollama", "modello")

    assert not stato_path.exists()
    assert not consulta_path.exists()


def test_ignora_una_riga_corrotta_nello_stato_senza_bloccarsi(tmp_path, monkeypatch):
    stato_path = tmp_path / "taggati.jsonl"
    stato_path.write_text("questo non e' json valido\n", encoding="utf-8")
    consulta_path = tmp_path / "Consulta.md"
    storico = [{"id": 1, "text": "primo"}]
    monkeypatch.setattr(watcher.api_client, "recupera_storico", lambda *a, **k: storico)
    monkeypatch.setattr(watcher.tagger, "genera_tag", lambda testo, host, modello: ["a", "b"])

    watcher.process_one_ciclo("http://esempio", str(stato_path), str(consulta_path), "http://ollama", "modello")

    contenuto = consulta_path.read_text(encoding="utf-8")
    assert "primo" in contenuto


def test_gestisce_errore_di_rete_durante_il_recupero(tmp_path, monkeypatch):
    stato_path = tmp_path / "taggati.jsonl"
    consulta_path = tmp_path / "Consulta.md"

    def recupero_rotto(*a, **k):
        raise RuntimeError("rete assente")

    monkeypatch.setattr(watcher.api_client, "recupera_storico", recupero_rotto)

    watcher.process_one_ciclo("http://esempio", str(stato_path), str(consulta_path), "http://ollama", "modello")

    assert not stato_path.exists()
    assert not consulta_path.exists()
