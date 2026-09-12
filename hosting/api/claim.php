<?php
// hosting/api/claim.php

require __DIR__ . '/db.php';

header('Content-Type: application/json');

require_api_key();

$db = get_db();
$db->beginTransaction();

try {
    $stmt = $db->prepare(
        'SELECT id, text FROM messaggi WHERE status = "pending" ORDER BY id ASC LIMIT 1 FOR UPDATE'
    );
    $stmt->execute();
    $riga = $stmt->fetch();

    if ($riga === false) {
        $db->commit();
        http_response_code(204);
        exit;
    }

    $update_stmt = $db->prepare('UPDATE messaggi SET status = "printing" WHERE id = :id');
    $update_stmt->execute(['id' => $riga['id']]);

    $db->commit();

    http_response_code(200);
    echo json_encode(['id' => (int) $riga['id'], 'text' => $riga['text']]);
} catch (Exception $e) {
    $db->rollBack();
    http_response_code(500);
    error_log('Errore durante il claim: ' . $e->getMessage());
    echo json_encode(['error' => 'Errore interno']);
}
