<?php
// hosting/api/history.php

require __DIR__ . '/db.php';

header('Content-Type: application/json');

$db = get_db();

$limit = isset($_GET['limit']) ? (int) $_GET['limit'] : 10;
$offset = isset($_GET['offset']) ? (int) $_GET['offset'] : 0;

$limit = max(1, min($limit, 100));
$offset = max(0, $offset);

$stmt = $db->prepare(
    'SELECT id, text, created_at, status, likes FROM messaggi
     WHERE status = "delivered"
     ORDER BY id DESC
     LIMIT :limit OFFSET :offset'
);
$stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
$stmt->bindValue(':offset', $offset, PDO::PARAM_INT);
$stmt->execute();
$righe = $stmt->fetchAll();

$messaggi = array_map(function ($riga) {
    return [
        'id' => (int) $riga['id'],
        'text' => $riga['text'],
        'created_at' => to_iso8601_utc($riga['created_at']),
        'status' => $riga['status'],
        'likes' => (int) $riga['likes'],
    ];
}, $righe);

echo json_encode(['messaggi' => $messaggi]);
