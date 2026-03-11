<?php
ini_set('display_errors', 1);
error_reporting(E_ALL);
header('Content-Type: text/plain');
echo 'PHP ' . PHP_VERSION . "\n";
echo 'Checking matrix.php syntax...' . "\n";
$out = shell_exec('php -l ' . escapeshellarg(__DIR__ . '/matrix.php') . ' 2>&1');
echo $out . "\n";
echo 'Done.' . "\n";
