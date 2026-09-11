# mondo-a-rotoli

Installazione interattiva: una pagina web dove le persone scrivono un
messaggio, che viene stampato su carta da una stampante USB collegata
a un Raspberry Pi Zero.

- `frontend/` — pagina web che raccoglie i messaggi
- `hosting/api/` — backend PHP + MySQL, deployato insieme a `frontend/`
  sullo stesso hosting condiviso
- `backend/` — poller Python sul Raspberry Pi, che interroga l'hosting
  ogni 5 secondi e stampa i nuovi messaggi
