-- hosting/schema.sql
CREATE TABLE IF NOT EXISTS messaggi (
  id INT AUTO_INCREMENT PRIMARY KEY,
  text VARCHAR(1000) NOT NULL,
  created_at DATETIME NOT NULL,
  status ENUM('pending', 'printing', 'delivered') NOT NULL DEFAULT 'pending',
  ip VARCHAR(45) NOT NULL,
  likes INT NOT NULL DEFAULT 0
) ENGINE=InnoDB;

CREATE INDEX idx_messaggi_status_id ON messaggi (status, id);
CREATE INDEX idx_messaggi_status_created_at ON messaggi (status, created_at);
CREATE INDEX idx_messaggi_ip_created_at ON messaggi (ip, created_at);

-- Log delle richieste di "mi piace", usato solo per il rate limit per IP
-- (un like non crea/modifica righe in "messaggi" oltre al contatore).
CREATE TABLE IF NOT EXISTS like_eventi (
  id INT AUTO_INCREMENT PRIMARY KEY,
  message_id INT NOT NULL,
  ip VARCHAR(45) NOT NULL,
  created_at DATETIME NOT NULL
) ENGINE=InnoDB;

CREATE INDEX idx_like_eventi_ip_created_at ON like_eventi (ip, created_at);
