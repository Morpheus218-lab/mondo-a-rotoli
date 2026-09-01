import printer


def test_crea_immagine_testo_ha_larghezza_pari_alla_larghezza_stampa():
    img = printer.crea_immagine_testo("ciao")
    # l'immagine viene ruotata di 90 gradi per la stampa verticale:
    # la larghezza finale corrisponde a LARGHEZZA_STAMPA (altezza prima della rotazione)
    assert img.width == printer.LARGHEZZA_STAMPA


def test_crea_immagine_testo_e_immagine_binaria():
    img = printer.crea_immagine_testo("ciao")
    assert img.mode == "1"


class StampanteFinta:
    def __init__(self):
        self.chiamate = []

    def set(self, **kwargs):
        self.chiamate.append(("set", kwargs))

    def text(self, testo):
        self.chiamate.append(("text", testo))

    def image(self, immagine):
        self.chiamate.append(("image", immagine))


def test_stampa_messaggio_normale_invia_intestazione_e_immagine():
    stampante = StampanteFinta()
    risultato = printer.stampa_messaggio(stampante, "ciao mondo")

    assert risultato is True
    nomi_chiamate = [nome for nome, _ in stampante.chiamate]
    assert nomi_chiamate == ["set", "text", "set", "image"]


def test_stampa_messaggio_troppo_lungo_stampa_avviso_invece_del_testo():
    stampante = StampanteFinta()
    testo_lungo = "a" * (printer.LIMITE_CARATTERI + 1)
    risultato = printer.stampa_messaggio(stampante, testo_lungo)

    assert risultato is True
    nomi_chiamate = [nome for nome, _ in stampante.chiamate]
    assert nomi_chiamate == ["set", "text", "set"]
    testo_stampato = stampante.chiamate[1][1]
    assert "TROPPO LUNGO" in testo_stampato


def test_stampa_messaggio_ritorna_false_se_la_stampante_solleva_eccezione():
    class StampanteRotta:
        def set(self, **kwargs):
            raise RuntimeError("USB scollegata")

    risultato = printer.stampa_messaggio(StampanteRotta(), "ciao")
    assert risultato is False
