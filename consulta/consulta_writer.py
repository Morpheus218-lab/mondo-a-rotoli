# consulta/consulta_writer.py
def formatta_entry(tag, testo):
    """Ritorna il blocco di testo per un singolo messaggio: una riga di
    tag nella forma [[tag1]], [[tag2]], ... seguita dal testo del
    messaggio."""
    riga_tag = ", ".join(f"[[{t}]]" for t in tag)
    return f"{riga_tag}\n{testo}\n"


def prepend_entry(path, tag, testo):
    """Scrive in testa a path (creandolo se non esiste) il blocco per
    questo messaggio, cosi' che i messaggi piu' recenti restino sempre in
    cima al file (ordine cronologico decrescente)."""
    blocco = formatta_entry(tag, testo)

    try:
        with open(path, "r", encoding="utf-8") as f:
            contenuto_precedente = f.read()
    except FileNotFoundError:
        contenuto_precedente = ""

    with open(path, "w", encoding="utf-8") as f:
        f.write(blocco + "\n" + contenuto_precedente)
