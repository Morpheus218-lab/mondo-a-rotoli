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
- `codice-binario.html` — installazione con telecamera: chi si mette
  davanti allo schermo viene reso come una griglia di cifre (la
  luminosità della webcam decide solo il colore di ogni cella, la cifra
  mostrata scorre dal flusso di bit reale degli ultimi messaggi). Legge
  `/api/history.php` come le altre pagine. Richiede un contesto sicuro
  (https, o `localhost` in sviluppo) perché usa la telecamera
  (`getUserMedia`): su http semplice il browser nega il permesso.

`index.html` e `codice-binario.html` condividono lo stesso sistema di
tema chiaro/scuro (`prefers-color-scheme`, con interruttore manuale che
sovrascrive e viene ricordato in `localStorage`).
