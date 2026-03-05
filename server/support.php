<?php
/**
 * Forge Support — FAQ + contact form
 * Forge itself handles Tier 1 support via this page.
 */
$page_title = 'Support — Forge';
$page_id = 'support';

// Handle contact form submission
$msg_sent = false;
$msg_error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['support_submit'])) {
    $email   = filter_var(trim($_POST['email'] ?? ''), FILTER_SANITIZE_EMAIL);
    $subject = htmlspecialchars(trim($_POST['subject'] ?? ''), ENT_QUOTES, 'UTF-8');
    $body    = htmlspecialchars(trim($_POST['body'] ?? ''), ENT_QUOTES, 'UTF-8');
    $account = htmlspecialchars(trim($_POST['account_id'] ?? ''), ENT_QUOTES, 'UTF-8');

    if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
        $msg_error = 'Please enter a valid email address.';
    } elseif (strlen($body) < 20) {
        $msg_error = 'Please describe your issue in a bit more detail.';
    } else {
        $to      = 'support@dirt-star.com';
        $headers = "From: Forge Support Form <noreply@dirt-star.com>\r\n"
                 . "Reply-To: $email\r\n"
                 . "Content-Type: text/plain; charset=UTF-8\r\n";
        $full_body = "From: $email\nAccount ID: $account\nSubject: $subject\n\n$body";
        if (mail($to, "[Forge Support] $subject", $full_body, $headers)) {
            $msg_sent = true;
        } else {
            $msg_error = 'Failed to send. Please email support@dirt-star.com directly.';
        }
    }
}

require_once __DIR__ . '/includes/header.php';
?>

<main class="legal-page">
<div class="legal-inner" style="max-width:800px">

<h1>Support</h1>
<p style="opacity:0.7">Forge is designed to mostly support itself — but we're here when you need us.</p>

<!-- ── FAQ ── -->
<section class="support-faq">
<h2>Common Questions</h2>

<details class="faq-item">
  <summary>Forge won't start / I get a black screen</summary>
  <div>
    <p>Usually a Python environment issue. From your Forge directory, run:</p>
    <pre><code>python -m forge</code></pre>
    <p>If that fails, check that your <code>.venv</code> is activated and dependencies are installed:</p>
    <pre><code>pip install -e .</code></pre>
    <p>On Windows, make sure you're using the venv Python, not the system stub:</p>
    <pre><code>.venv\Scripts\python.exe -m forge</code></pre>
  </div>
</details>

<details class="faq-item">
  <summary>Forge says I have a Community license but I paid for Pro/Power</summary>
  <div>
    <p>Your passport file needs to be placed in <code>~/.forge/passport.json</code>. Check your download email for the passport file. If you've lost it, email us with your order ID and we'll re-issue it.</p>
    <p>Once the file is in place, restart Forge and run <code>/passport</code> to verify your license.</p>
  </div>
</details>

<details class="faq-item">
  <summary>How do I activate on a new machine?</summary>
  <div>
    <p>Copy your <code>~/.forge/passport.json</code> to the new machine and run <code>/activate</code>. If you're out of seats, email us and we can transfer an activation.</p>
  </div>
</details>

<details class="faq-item">
  <summary>Ollama isn't connecting</summary>
  <div>
    <p>Make sure Ollama is running before starting Forge:</p>
    <pre><code>ollama serve</code></pre>
    <p>Then confirm your model is pulled:</p>
    <pre><code>ollama pull qwen2.5-coder:14b</code></pre>
    <p>Forge connects to Ollama at <code>http://localhost:11434</code> by default. If you're running Ollama on a different port, update <code>ollama_host</code> in <code>~/.forge/config.yaml</code>.</p>
  </div>
</details>

<details class="faq-item">
  <summary>How do I get a refund?</summary>
  <div>
    <p>See our <a href="refund.php">Refund Policy</a>. Licenses are non-refundable after activation. If something isn't working and we can't fix it within 14 days, we'll make it right. Email us with your order ID.</p>
  </div>
</details>

<details class="faq-item">
  <summary>Can I transfer my license to someone else?</summary>
  <div>
    <p>Licenses are personal and non-transferable per our <a href="terms.php">Terms of Service</a>. Seats can be moved between your own machines — email us for a seat transfer.</p>
  </div>
</details>

<details class="faq-item">
  <summary>Is my code sent anywhere?</summary>
  <div>
    <p>No. With local AI (Ollama, default), your code never leaves your machine. Telemetry is disabled by default. See our <a href="privacy.php">Privacy Policy</a> for the full breakdown.</p>
  </div>
</details>

<details class="faq-item">
  <summary>How do I update Forge?</summary>
  <div>
    <p>From inside Forge, run <code>/update</code>. This pulls the latest version from the Origin repository and restarts. Or manually: <code>git pull && pip install -e .</code></p>
  </div>
</details>

<details class="faq-item">
  <summary>Where is my config / passport / genome stored?</summary>
  <div>
    <ul>
      <li>Config: <code>~/.forge/config.yaml</code></li>
      <li>Passport: <code>~/.forge/passport.json</code></li>
      <li>Genome: <code>~/.forge/genome/</code></li>
      <li>Memory: <code>~/.forge/memory/</code></li>
    </ul>
  </div>
</details>

<details class="faq-item">
  <summary>Forge is slow — how do I speed it up?</summary>
  <div>
    <p>Performance depends almost entirely on your GPU. Recommendations:</p>
    <ul>
      <li>Use <code>qwen2.5-coder:14b</code> (recommended) or drop to <code>7b</code> on lower VRAM</li>
      <li>Keep Ollama and Forge on the same machine — no network overhead</li>
      <li>Close other GPU-heavy applications while Forge is running</li>
      <li>Enable Flash Attention in Ollama if your GPU supports it</li>
    </ul>
  </div>
</details>

</section>

<!-- ── Contact Form ── -->
<section class="support-contact" style="margin-top:3rem">
<h2>Still need help?</h2>

<?php if ($msg_sent): ?>
  <div class="alert alert-success" style="padding:16px;border-radius:8px;background:rgba(63,185,80,0.15);border:1px solid #3fb950;margin-bottom:24px">
    Message sent. We'll get back to you within 1 business day.
  </div>
<?php elseif ($msg_error): ?>
  <div class="alert alert-error" style="padding:16px;border-radius:8px;background:rgba(248,81,73,0.15);border:1px solid #f85149;margin-bottom:24px">
    <?php echo $msg_error; ?>
  </div>
<?php endif; ?>

<?php if (!$msg_sent): ?>
<form method="POST" class="support-form" style="display:flex;flex-direction:column;gap:16px">
  <div class="form-group">
    <label for="email">Your email</label>
    <input type="email" id="email" name="email" required placeholder="you@example.com"
           value="<?php echo htmlspecialchars($_POST['email'] ?? '', ENT_QUOTES); ?>">
  </div>
  <div class="form-group">
    <label for="account_id">Account / Order ID <span style="opacity:0.5">(optional, helps us find your license)</span></label>
    <input type="text" id="account_id" name="account_id" placeholder="pp-abc123 or order number"
           value="<?php echo htmlspecialchars($_POST['account_id'] ?? '', ENT_QUOTES); ?>">
  </div>
  <div class="form-group">
    <label for="subject">Subject</label>
    <input type="text" id="subject" name="subject" required placeholder="What's going on?"
           value="<?php echo htmlspecialchars($_POST['subject'] ?? '', ENT_QUOTES); ?>">
  </div>
  <div class="form-group">
    <label for="body">Details</label>
    <textarea id="body" name="body" rows="6" required
              placeholder="Describe the issue — what happened, what you expected, what you tried..."><?php echo htmlspecialchars($_POST['body'] ?? '', ENT_QUOTES); ?></textarea>
  </div>
  <button type="submit" name="support_submit" class="btn btn-primary" style="align-self:flex-start">Send Message</button>
</form>
<?php endif; ?>

<p style="margin-top:16px;opacity:0.5;font-size:0.85rem">Or email directly: <a href="mailto:support@dirt-star.com">support@dirt-star.com</a></p>
</section>

</div>
</main>

<style>
.faq-item {
    border-bottom: 1px solid rgba(255,255,255,0.07);
    padding: 4px 0;
}
.faq-item summary {
    cursor: pointer;
    padding: 14px 0;
    font-weight: 500;
    list-style: none;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.faq-item summary::after {
    content: '+';
    opacity: 0.4;
    font-size: 1.2rem;
    transition: transform 0.2s;
}
.faq-item[open] summary::after {
    content: '−';
}
.faq-item div {
    padding: 0 0 16px 0;
    opacity: 0.8;
    line-height: 1.7;
}
.faq-item pre {
    background: rgba(255,255,255,0.05);
    border-radius: 6px;
    padding: 10px 14px;
    overflow-x: auto;
    margin: 8px 0;
}
.support-form input,
.support-form textarea {
    width: 100%;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 10px 14px;
    color: inherit;
    font: inherit;
    font-size: 0.95rem;
    box-sizing: border-box;
    transition: border-color 0.2s;
}
.support-form input:focus,
.support-form textarea:focus {
    outline: none;
    border-color: var(--accent, #00d4ff);
}
.support-form label {
    display: block;
    margin-bottom: 6px;
    font-size: 0.9rem;
    opacity: 0.8;
}
</style>

<?php require_once __DIR__ . '/includes/footer.php'; ?>
