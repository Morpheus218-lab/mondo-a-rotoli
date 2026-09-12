-- hosting/schema.sql
CREATE TABLE IF NOT EXISTS messaggi (
  id INT AUTO_INCREMENT PRIMARY KEY,
  text VARCHAR(1000) NOT NULL,
  created_at DATETIME NOT NULL,
  status ENUM('pending', 'printing', 'delivered') NOT NULL DEFAULT 'pending',
  ip VARCHAR(45) NOT NULL
) ENGINE=InnoDB;

CREATE INDEX idx_messaggi_status_id ON messaggi (status, id);
CREATE INDEX idx_messaggi_ip_created_at ON messaggi (ip, created_at);
