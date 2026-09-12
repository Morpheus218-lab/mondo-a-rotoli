<?php
// hosting/api/message.php

require __DIR__ . '/db.php';

header('Content-Type: application/json');

$config = get_config();
$db = get_db();

$LIMITE_BODY_BYTE = 64 * 1024;
$corpo_raw = file_get_contents('php://input');

if (strlen($corpo_raw) > $LIMITE_BODY_BYTE) {
    http_response_code(413);
    echo json_encode(['error' => 'Corpo della richiesta troppo grande']);
    exit;
}

$corpo = json_decode($corpo_raw, true);

if (!is_array($corpo) || !isset($corpo['text']) || !is_string($corpo['text'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Il campo "text" è obbligatorio']);
    exit;
}

$testo = trim($corpo['text']);

if ($testo === '') {
    http_response_code(400);
    echo json_encode(['error' => 'Il campo "text" è obbligatorio']);
    exit;
}

if (mb_strlen($testo) > 1000) {
    http_response_code(400);
    echo json_encode(['error' => 'Il campo "text" supera il limite di 1000 caratteri']);
    exit;
}

$ip = $_SERVER['REMOTE_ADDR'] ?? '';
$finestra_da = gmdate(
    'Y-m-d H:i:s',
    time() - $config['rate_limit_finestra_minuti'] * 60
);

$conteggio_stmt = $db->prepare(
    'SELECT COUNT(*) FROM messaggi WHERE ip = :ip AND created_at >= :da'
);
$conteggio_stmt->execute(['ip' => $ip, 'da' => $finestra_da]);
$conteggio = (int) $conteggio_stmt->fetchColumn();

if ($conteggio >= $config['rate_limit_max_messaggi']) {
    http_response_code(429);
    echo json_encode(['error' => 'Troppi messaggi inviati, riprova tra qualche minuto']);
    exit;
}

$created_at_db = utc_now_mysql();

$insert_stmt = $db->prepare(
    'INSERT INTO messaggi (text, created_at, status, ip) VALUES (:text, :created_at, "pending", :ip)'
);
$insert_stmt->execute(['text' => $testo, 'created_at' => $created_at_db, 'ip' => $ip]);

http_response_code(202);
echo json_encode([
    'ok' => true,
    'id' => (int) $db->lastInsertId(),
    'createdAt' => to_iso8601_utc($created_at_db),
]);
