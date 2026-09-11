<?php
// hosting/api/db.php

function get_config(): array
{
    $config_path = __DIR__ . '/config.php';
    if (!file_exists($config_path)) {
        http_response_code(500);
        header('Content-Type: application/json');
        error_log('config.php mancante: copiare config.php.example e compilarlo');
        echo json_encode(['error' => 'Errore di configurazione del server']);
        exit;
    }
    return require $config_path;
}

function get_db(): PDO
{
    $config = get_config();
    $dsn = sprintf(
        'mysql:host=%s;dbname=%s;charset=utf8mb4',
        $config['db_host'],
        $config['db_name']
    );

    try {
        return new PDO($dsn, $config['db_user'], $config['db_pass'], [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
    } catch (PDOException $e) {
        http_response_code(500);
        header('Content-Type: application/json');
        error_log('Connessione al DB fallita: ' . $e->getMessage());
        echo json_encode(['error' => 'Errore di connessione al database']);
        exit;
    }
}

function require_api_key(): void
{
    $config = get_config();
    $chiave_fornita = $_SERVER['HTTP_X_API_KEY'] ?? '';

    if (!hash_equals($config['api_key'], $chiave_fornita)) {
        http_response_code(401);
        header('Content-Type: application/json');
        echo json_encode(['error' => 'Non autorizzato']);
        exit;
    }
}

function utc_now_mysql(): string
{
    return (new DateTimeImmutable('now', new DateTimeZone('UTC')))->format('Y-m-d H:i:s');
}

function to_iso8601_utc(string $mysql_datetime): string
{
    $dt = DateTime::createFromFormat('Y-m-d H:i:s', $mysql_datetime, new DateTimeZone('UTC'));
    return $dt->format('Y-m-d\TH:i:s\Z');
}
