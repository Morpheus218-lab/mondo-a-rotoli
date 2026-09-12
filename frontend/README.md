# frontend

Pagine statiche dell'installazione. Vanno deployate sullo stesso hosting
condiviso del backend PHP (vedi `../hosting/README.md`): il campo
`API_URL` è un percorso relativo (`/api`), quindi non richiedono alcuna
modifica per-deploy.

- `index.html` — pagina principale: form per scrivere un messaggio +
  storico degli ultimi messaggi stampati (infinite scroll, 10 alla
  volta).
- `storico.html` — pagina di sola lettura con **solo** lo storico
  completo dei messaggi stampati, stesso infinite scroll di `index.html`
  ma senza il form di invio. Utile per uno schermo dedicato o un archivio
  pubblico separato dalla pagina di invio.
