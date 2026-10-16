# consulta/git_publisher.py
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

NOME_FILE_REMOTO = "Consulta.md"


def _esegui(comando, cwd):
    return subprocess.run(comando, cwd=cwd, check=True, capture_output=True, text=True)


def _imposta_identita_locale(clone_dir, nome_commit, email_commit):
    """Imposta user.name/user.email solo nella config locale di
    clone_dir (file .git/config), senza toccare la config globale della
    macchina: necessaria per poter fare commit automatici senza
    dipendere da un'identita' git impostata altrove per altri scopi."""
    _esegui(["git", "config", "user.name", nome_commit], cwd=clone_dir)
    _esegui(["git", "config", "user.email", email_commit], cwd=clone_dir)


def assicura_clone(remote_url, clone_dir, nome_commit=None, email_commit=None):
    """Clona remote_url in clone_dir se non esiste ancora (richiede che
    l'autenticazione verso remote_url, es. una chiave SSH gia' autorizzata,
    funzioni senza richiedere input interattivo). Se nome_commit e
    email_commit sono forniti, imposta l'identita' per i commit solo
    nella config locale del clone, sia su un clone nuovo sia su uno gia'
    esistente."""
    if os.path.isdir(os.path.join(clone_dir, ".git")):
        if nome_commit and email_commit:
            _imposta_identita_locale(clone_dir, nome_commit, email_commit)
        return

    cartella_padre = os.path.dirname(os.path.abspath(clone_dir))
    os.makedirs(cartella_padre, exist_ok=True)
    _esegui(["git", "clone", remote_url, clone_dir], cwd=cartella_padre)

    if nome_commit and email_commit:
        _imposta_identita_locale(clone_dir, nome_commit, email_commit)


def _ha_commit_non_pushati(clone_dir, branch):
    """True se HEAD e' avanti rispetto a origin/branch (es. un push
    precedente fallito a meta', dopo che il commit era gia' andato a
    buon fine)."""
    risultato = _esegui(["git", "rev-list", f"origin/{branch}..HEAD", "--count"], cwd=clone_dir)
    return int(risultato.stdout.strip()) > 0


def pubblica(clone_dir, consulta_path, branch):
    """Aggiorna clone_dir dal remoto, copia consulta_path su
    clone_dir/Consulta.md e, se il contenuto e' cambiato rispetto
    all'ultimo commit, fa commit. Fa comunque push se HEAD risulta avanti
    rispetto a origin/branch, cosi' un push fallito in un giro precedente
    (dopo che il commit era gia' riuscito) viene ritentato anche quando il
    contenuto non e' cambiato nel frattempo. Ritorna True se ha pushato
    qualcosa, False se non c'era nulla di nuovo da pubblicare."""
    _esegui(["git", "pull", "--ff-only", "origin", branch], cwd=clone_dir)

    destinazione = os.path.join(clone_dir, NOME_FILE_REMOTO)
    shutil.copyfile(consulta_path, destinazione)

    stato = _esegui(["git", "status", "--porcelain", "--", NOME_FILE_REMOTO], cwd=clone_dir)
    if stato.stdout.strip():
        _esegui(["git", "add", "--", NOME_FILE_REMOTO], cwd=clone_dir)
        _esegui(["git", "commit", "-m", "Aggiorna Consulta.md"], cwd=clone_dir)
    elif not _ha_commit_non_pushati(clone_dir, branch):
        return False

    _esegui(["git", "push", "origin", branch], cwd=clone_dir)
    return True
