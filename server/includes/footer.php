
<!-- ── Footer ── -->
<footer class="footer">
    <div class="footer-links">
        <a href="/Forge/">Home</a>
        <a href="docs.php">Documentation</a>
        <a href="status.php">Status</a>
        <a href="support.php">Support</a>
        <a href="account.php">Account</a>
    </div>
    <div class="footer-legal">
        <a href="terms.php">Terms of Service</a>
        <a href="privacy.php">Privacy Policy</a>
        <a href="refund.php">Refund Policy</a>
    </div>
    <p class="footer-copy">&copy; <?php echo date('Y'); ?> Forge by Dirt Star. All rights reserved.</p>
</footer>

<script src="assets/app.js?v=<?php echo filemtime(__DIR__ . '/../assets/app.js'); ?>"></script>
<script src="assets/tracker.js?v=<?php echo filemtime(__DIR__ . '/../assets/tracker.js'); ?>"></script>
</body>
</html>
