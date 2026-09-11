<?php
// hosting/api/ack.php

require __DIR__ . '/db.php';

header('Content-Type: application/json');

require_api_key();

$db = get_db();

$corpo = json_decode(file_get_contents('php://input'), true);

if (!is_array($corpo) || !isset($corpo['id']) || !is_int($corpo['id'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Il campo "id" è obbligatorio']);
    exit;
}

$stmt = $db->prepare(
    'UPDATE messaggi SET status = "delivered" WHERE id = :id AND status = "printing"'
);
$stmt->execute(['id' => $corpo['id']]);

if ($stmt->rowCount() === 0) {
    http_response_code(404);
    echo json_encode(['error' => 'Messaggio non trovato o non in stato printing']);
    exit;
}

http_response_code(200);
echo json_encode(['ok' => true]);
