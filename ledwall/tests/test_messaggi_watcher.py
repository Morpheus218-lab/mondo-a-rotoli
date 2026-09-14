# ledwall/tests/test_messaggi_watcher.py
import json
import os
import time
from collections import deque

import messaggi_watcher


def scrivi_jsonl(path, messaggi):
    path.write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in messaggi) + "\n", encoding="utf-8"
    )


def test_trova_file_messaggi_ordina_per_data_di_modifica(tmp_path):
    vecchio = tmp_path / "messaggi.jsonl"
    nuovo = tmp_path / "messaggi #1.jsonl"
    vecchio.write_text("{}", encoding="utf-8")
    time.sleep(0.01)
    nuovo.write_text("{}", encoding="utf-8")
    (tmp_path / "altro.txt").write_text("non e' un messaggio", encoding="utf-8")

    trovati = messaggi_watcher.trova_file_messaggi(str(tmp_path))

    assert [os.path.basename(p) for p in trovati] == ["messaggi.jsonl", "messaggi #1.jsonl"]


def test_carica_id_mostrati_ritorna_insieme_vuoto_se_il_file_non_esiste(tmp_path):
    assert messaggi_watcher.carica_id_mostrati(str(tmp_path / "mostrati.jsonl")) == set()


def test_carica_id_mostrati_legge_gli_id_gia_presenti(tmp_path):
    file_stato = tmp_path / "mostrati.jsonl"
    scrivi_jsonl(file_stato, [{"id": 1, "text": "a"}, {"id": 2, "text": "b"}])

    assert messaggi_watcher.carica_id_mostrati(str(file_stato)) == {1, 2}


def test_carica_id_mostrati_ignora_una_riga_corrotta(tmp_path):
    file_stato = tmp_path / "mostrati.jsonl"
    file_stato.write_text(
        json.dumps({"id": 1, "text": "a"}) + "\nnon e' json valido\n", encoding="utf-8"
    )

    assert messaggi_watcher.carica_id_mostrati(str(file_stato)) == {1}


def test_estrai_nuovi_ritorna_solo_i_messaggi_non_gia_mostrati(tmp_path):
    path = tmp_path / "messaggi.jsonl"
    scrivi_jsonl(path, [{"id": 3, "text": "c"}, {"id": 2, "text": "b"}, {"id": 1, "text": "a"}])

    nuovi = messaggi_watcher.estrai_nuovi(str(path), {1})

    assert [m["id"] for m in nuovi] == [2, 3]  # dal piu' vecchio al piu' nuovo


def test_elabora_cartella_estrae_messaggi_di_piu_file_e_aggiorna_lo_stato(tmp_path):
    cartella = tmp_path / "ricevuti"
    cartella.mkdir()
    file_stato = tmp_path / "mostrati.jsonl"
    scrivi_jsonl(cartella / "messaggi.jsonl", [{"id": 1, "text": "a"}, {"id": 2, "text": "b"}])
    time.sleep(0.01)
    scrivi_jsonl(cartella / "messaggi #1.jsonl", [{"id": 2, "text": "b"}, {"id": 3, "text": "c"}])

    nuovi = messaggi_watcher.elabora_cartella(str(cartella), str(file_stato))

    assert [m["id"] for m in nuovi] == [1, 2, 3]
    assert messaggi_watcher.carica_id_mostrati(str(file_stato)) == {1, 2, 3}


def test_elabora_cartella_cancella_i_file_sorgente(tmp_path):
    cartella = tmp_path / "ricevuti"
    cartella.mkdir()
    file_stato = tmp_path / "mostrati.jsonl"
    percorso = cartella / "messaggi.jsonl"
    scrivi_jsonl(percorso, [{"id": 1, "text": "a"}])

    messaggi_watcher.elabora_cartella(str(cartella), str(file_stato))

    assert not percorso.exists()


def test_elabora_cartella_cancella_anche_se_non_ci_sono_messaggi_nuovi(tmp_path):
    cartella = tmp_path / "ricevuti"
    cartella.mkdir()
    file_stato = tmp_path / "mostrati.jsonl"
    scrivi_jsonl(file_stato, [{"id": 1, "text": "a"}])
    percorso = cartella / "messaggi.jsonl"
    scrivi_jsonl(percorso, [{"id": 1, "text": "a"}])  # gia' tutto visto

    nuovi = messaggi_watcher.elabora_cartella(str(cartella), str(file_stato))

    assert nuovi == []
    assert not percorso.exists()


def test_elabora_cartella_su_cartella_vuota_ritorna_lista_vuota(tmp_path):
    cartella = tmp_path / "ricevuti"
    cartella.mkdir()
    file_stato = tmp_path / "mostrati.jsonl"

    assert messaggi_watcher.elabora_cartella(str(cartella), str(file_stato)) == []


def test_prossimo_testo_automatico_aspetta_il_timeout_dall_ultimo_input_manuale():
    coda = deque([{"id": 1, "text": "a"}])

    risultato = messaggi_watcher.prossimo_testo_automatico(
        coda, ultimo_input_manuale=100.0, inizio_messaggio_corrente=None,
        ora=105.0, idle_timeout_manuale=15.0, durata_messaggio_auto=8.0,
    )

    assert risultato is None
    assert len(coda) == 1  # non consumato


def test_prossimo_testo_automatico_parte_subito_se_non_c_e_nulla_in_mostra():
    coda = deque([{"id": 1, "text": "a"}])

    risultato = messaggi_watcher.prossimo_testo_automatico(
        coda, ultimo_input_manuale=0.0, inizio_messaggio_corrente=None,
        ora=1000.0, idle_timeout_manuale=15.0, durata_messaggio_auto=8.0,
    )

    assert risultato == {"id": 1, "text": "a"}
    assert len(coda) == 0  # consumato


def test_prossimo_testo_automatico_aspetta_la_durata_del_messaggio_corrente():
    coda = deque([{"id": 2, "text": "b"}])

    risultato = messaggi_watcher.prossimo_testo_automatico(
        coda, ultimo_input_manuale=0.0, inizio_messaggio_corrente=1000.0,
        ora=1003.0, idle_timeout_manuale=15.0, durata_messaggio_auto=8.0,
    )

    assert risultato is None
    assert len(coda) == 1


def test_prossimo_testo_automatico_avanza_dopo_la_durata_del_messaggio_corrente():
    coda = deque([{"id": 2, "text": "b"}])

    risultato = messaggi_watcher.prossimo_testo_automatico(
        coda, ultimo_input_manuale=0.0, inizio_messaggio_corrente=1000.0,
        ora=1008.0, idle_timeout_manuale=15.0, durata_messaggio_auto=8.0,
    )

    assert risultato == {"id": 2, "text": "b"}


def test_prossimo_testo_automatico_ritorna_none_se_la_coda_e_vuota():
    coda = deque()

    risultato = messaggi_watcher.prossimo_testo_automatico(
        coda, ultimo_input_manuale=0.0, inizio_messaggio_corrente=None,
        ora=1000.0, idle_timeout_manuale=15.0, durata_messaggio_auto=8.0,
    )

    assert risultato is None
