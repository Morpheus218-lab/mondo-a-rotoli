# consulta/tests/test_consulta_writer.py
import consulta_writer


def test_formatta_entry_unisce_i_tag_tra_doppie_parentesi():
    blocco = consulta_writer.formatta_entry(["saluti", "amicizia"], "ciao mondo")
    assert blocco == "[[saluti]], [[amicizia]]\nciao mondo\n"


def test_prepend_entry_crea_il_file_se_non_esiste(tmp_path):
    path = tmp_path / "Consulta.md"
    consulta_writer.prepend_entry(str(path), ["tag1", "tag2"], "primo messaggio")

    assert path.read_text(encoding="utf-8") == "[[tag1]], [[tag2]]\nprimo messaggio\n\n"


def test_prepend_entry_mette_il_nuovo_messaggio_in_testa(tmp_path):
    path = tmp_path / "Consulta.md"
    path.write_text("[[vecchio]]\nmessaggio vecchio\n\n", encoding="utf-8")

    consulta_writer.prepend_entry(str(path), ["nuovo"], "messaggio nuovo")

    contenuto = path.read_text(encoding="utf-8")
    assert contenuto.startswith("[[nuovo]]\nmessaggio nuovo\n\n")
    assert contenuto.endswith("[[vecchio]]\nmessaggio vecchio\n\n")
