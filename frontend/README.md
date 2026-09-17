# frontend

Pagine statiche dell'installazione. Vanno deployate sullo stesso hosting
condiviso del backend PHP (vedi `../hosting/README.md`): il campo
`API_URL` è un percorso relativo (`/api`), quindi non richiedono alcuna
modifica per-deploy.

- `index.html` — pagina principale: form per scrivere un messaggio +
  storico degli ultimi messaggi stampati, con tre viste (rotolo, lista,
  binario — quest'ultima mostra ogni messaggio come griglia di bit
  UTF-8 reali). Include anche "UTOPIA 01": una sezione con telecamera,
  attivabile dal bottone "Guarda il codice binario", che mostra
  affiancate la ripresa dal vivo e la sua traduzione in una griglia
  16×16 — il colore di ogni cella viene dalla luminosità
  dell'inquadratura, la cifra mostrata è invece un bit vero, preso dal
  flusso dei messaggi scritti da chi è passato prima. Richiede un
  contesto sicuro (https, o `localhost` in sviluppo) per la telecamera
  (`getUserMedia`): su http semplice il browser nega il permesso.
- `storico.html` — pagina di sola lettura con **solo** lo storico
  completo dei messaggi stampati, stesso infinite scroll di `index.html`
  ma senza il form di invio. Utile per uno schermo dedicato o un archivio
  pubblico separato dalla pagina di invio.

`index.html` ha un tema chiaro/scuro che segue il telefono di chi guarda
(`prefers-color-scheme`); un interruttore in alto a sinistra permette di
scegliere esplicitamente, scelta poi ricordata in `localStorage`.
