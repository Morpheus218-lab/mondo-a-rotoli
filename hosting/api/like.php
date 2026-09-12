<?php
// hosting/api/like.php

require __DIR__ . '/db.php';

header('Content-Type: application/json');

$config = get_config();
$db = get_db();

$corpo = json_decode(file_get_contents('php://input'), true);

if (!is_array($corpo) || !isset($corpo['id']) || !is_int($corpo['id'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Il campo "id" è obbligatorio']);
    exit;
}

$ip = $_SERVER['REMOTE_ADDR'] ?? '';
$finestra_da = gmdate(
    'Y-m-d H:i:s',
    time() - $config['rate_limit_finestra_like_minuti'] * 60
);

$conteggio_stmt = $db->prepare(
    'SELECT COUNT(*) FROM like_eventi WHERE ip = :ip AND created_at >= :da'
);
$conteggio_stmt->execute(['ip' => $ip, 'da' => $finestra_da]);
$conteggio = (int) $conteggio_stmt->fetchColumn();

if ($conteggio >= $config['rate_limit_max_like']) {
    http_response_code(429);
    echo json_encode(['error' => 'Troppi "mi piace" inviati, riprova tra qualche minuto']);
    exit;
}

$update_stmt = $db->prepare(
    'UPDATE messaggi SET likes = likes + 1 WHERE id = :id AND status = "delivered"'
);
$update_stmt->execute(['id' => $corpo['id']]);

if ($update_stmt->rowCount() === 0) {
    http_response_code(404);
    echo json_encode(['error' => 'Messaggio non trovato o non ancora stampato']);
    exit;
}

$log_stmt = $db->prepare(
    'INSERT INTO like_eventi (message_id, ip, created_at) VALUES (:message_id, :ip, :created_at)'
);
$log_stmt->execute(['message_id' => $corpo['id'], 'ip' => $ip, 'created_at' => utc_now_mysql()]);

$conteggio_like_stmt = $db->prepare('SELECT likes FROM messaggi WHERE id = :id');
$conteggio_like_stmt->execute(['id' => $corpo['id']]);
$likes_totali = (int) $conteggio_like_stmt->fetchColumn();

http_response_code(200);
echo json_encode(['likes' => $likes_totali]);
