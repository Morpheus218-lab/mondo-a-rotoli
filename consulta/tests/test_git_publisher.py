# consulta/tests/test_git_publisher.py
import subprocess

import git_publisher


def _git(comando, cwd):
    subprocess.run(["git"] + comando, cwd=cwd, check=True, capture_output=True, text=True)


def _crea_remote_bare(tmp_path):
    remote_dir = tmp_path / "remote.git"
    _git(["init", "--bare", "-b", "main", str(remote_dir)], cwd=str(tmp_path))
    return str(remote_dir)


def _clona_e_configura(remote_url, clone_dir):
    _git(["clone", remote_url, str(clone_dir)], cwd=str(clone_dir.parent))
    _git(["config", "user.email", "test@esempio.it"], cwd=str(clone_dir))
    _git(["config", "user.name", "Test"], cwd=str(clone_dir))
    # Un repo bare appena creato non ha commit: senza un primo commit "pull
    # --ff-only" non avrebbe nulla da confrontare.
    (clone_dir / "README.md").write_text("repo remoto di consulta\n", encoding="utf-8")
    _git(["add", "README.md"], cwd=str(clone_dir))
    _git(["commit", "-m", "init"], cwd=str(clone_dir))
    _git(["push", "origin", "main"], cwd=str(clone_dir))


def test_assicura_clone_clona_se_non_esiste(tmp_path):
    remote_url = _crea_remote_bare(tmp_path)
    clone_dir = tmp_path / "clone"

    git_publisher.assicura_clone(remote_url, str(clone_dir))

    assert (clone_dir / ".git").is_dir()


def _leggi_config_locale(clone_dir, chiave):
    risultato = subprocess.run(
        ["git", "config", "--local", chiave], cwd=str(clone_dir), capture_output=True, text=True
    )
    return risultato.stdout.strip()


def test_assicura_clone_imposta_identita_locale_su_un_clone_nuovo(tmp_path):
    remote_url = _crea_remote_bare(tmp_path)
    clone_dir = tmp_path / "clone"

    git_publisher.assicura_clone(remote_url, str(clone_dir), "Consulta Watcher", "consulta@esempio.it")

    assert _leggi_config_locale(clone_dir, "user.name") == "Consulta Watcher"
    assert _leggi_config_locale(clone_dir, "user.email") == "consulta@esempio.it"
    # Non deve toccare la config globale della macchina.
    globale = subprocess.run(
        ["git", "config", "--global", "--get", "user.name"], capture_output=True, text=True
    )
    assert "Consulta Watcher" not in globale.stdout


def test_assicura_clone_imposta_identita_locale_anche_su_un_clone_gia_esistente(tmp_path):
    remote_url = _crea_remote_bare(tmp_path)
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()
    _clona_e_configura(remote_url, clone_dir)  # identita' diversa gia' impostata

    git_publisher.assicura_clone(remote_url, str(clone_dir), "Consulta Watcher", "consulta@esempio.it")

    assert _leggi_config_locale(clone_dir, "user.name") == "Consulta Watcher"
    assert _leggi_config_locale(clone_dir, "user.email") == "consulta@esempio.it"


def test_assicura_clone_non_fa_nulla_se_gia_clonato(tmp_path):
    remote_url = _crea_remote_bare(tmp_path)
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()
    _clona_e_configura(remote_url, clone_dir)

    git_publisher.assicura_clone(remote_url, str(clone_dir))  # non deve sollevare


def test_pubblica_fa_commit_e_push_se_il_contenuto_e_cambiato(tmp_path):
    remote_url = _crea_remote_bare(tmp_path)
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()
    _clona_e_configura(remote_url, clone_dir)

    consulta_path = tmp_path / "Consulta.md"
    consulta_path.write_text("[[saluti]]\nciao mondo\n", encoding="utf-8")

    pubblicato = git_publisher.pubblica(str(clone_dir), str(consulta_path), "main")

    assert pubblicato is True
    assert (clone_dir / "Consulta.md").read_text(encoding="utf-8") == "[[saluti]]\nciao mondo\n"

    # Verifica che sia arrivato davvero sul remoto, clonandolo di nuovo altrove.
    verifica_dir = tmp_path / "verifica"
    _git(["clone", remote_url, str(verifica_dir)], cwd=str(tmp_path))
    assert (verifica_dir / "Consulta.md").read_text(encoding="utf-8") == "[[saluti]]\nciao mondo\n"


def test_pubblica_ritorna_false_se_nulla_e_cambiato(tmp_path):
    remote_url = _crea_remote_bare(tmp_path)
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()
    _clona_e_configura(remote_url, clone_dir)

    consulta_path = tmp_path / "Consulta.md"
    consulta_path.write_text("[[saluti]]\nciao mondo\n", encoding="utf-8")

    assert git_publisher.pubblica(str(clone_dir), str(consulta_path), "main") is True
    assert git_publisher.pubblica(str(clone_dir), str(consulta_path), "main") is False
