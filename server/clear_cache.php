<?php
$cache = __DIR__ . '/data/matrix_cache.json';
if (file_exists($cache)) { unlink($cache); echo 'cleared'; } else { echo 'no cache'; }
