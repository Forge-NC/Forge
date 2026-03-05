<?php
$page_title = 'Privacy Policy — Forge';
$page_id = 'privacy';
require_once __DIR__ . '/includes/header.php';
?>

<main class="legal-page">
<div class="legal-inner">

<h1>Privacy Policy</h1>
<p class="legal-date">Effective: January 1, 2026 &mdash; Last updated: March 2026</p>

<p>Forge is built on a simple principle: your code and your AI conversations are yours. This policy explains exactly what we collect, what we don't, and why.</p>

<h2>1. Who We Are</h2>
<p>Forge is developed and operated by Dirt Star ("we," "us," "our"), based in Wisconsin, USA. Contact: <a href="mailto:privacy@dirt-star.com">privacy@dirt-star.com</a></p>

<h2>2. What We Collect and Why</h2>

<h3>2a. Waitlist Email Address</h3>
<p>When you join the waitlist, we collect your email address. We use it only to notify you when Forge is available. We do not sell, rent, or share it with third parties. You can unsubscribe at any time by emailing <a href="mailto:privacy@dirt-star.com">privacy@dirt-star.com</a>.</p>

<h3>2b. Machine Identifier (License Activation)</h3>
<p>When you activate a paid license, Forge generates a stable, anonymous machine identifier (a random hex string derived from your hardware) and sends it to our server once to associate it with your license. This identifier contains no personally identifiable information — it is not your name, IP address, or hardware serial number. After activation, license verification happens entirely offline on your device.</p>

<h3>2c. Telemetry (Opt-In Only — Disabled by Default)</h3>
<p>Forge includes an optional telemetry system that is <strong>disabled by default</strong>. You must explicitly enable it in your configuration (<code>telemetry_enabled: true</code>). If enabled, Forge may send a redacted audit bundle to our server at the end of a session. This bundle:</p>
<ul>
  <li>Does <strong>not</strong> contain your code, file contents, AI prompts, or AI responses</li>
  <li>Does contain session metadata: model used, turn count, tool call counts, error types, hardware summary (GPU name, VRAM), Forge version, and current working directory path</li>
  <li>Is capped at 512KB per upload</li>
  <li>Is rate-limited to 10 uploads per machine per hour</li>
</ul>
<p>Telemetry data is used solely to improve Forge's reliability and performance. It is not shared with third parties.</p>

<h3>2d. Threat Intelligence Updates (Outbound Only)</h3>
<p>If you configure a threat signature URL (<code>threat_signatures_url</code>), Forge will periodically fetch updated security signature definitions from that URL. This is an outbound-only request: Forge downloads data but sends no user data to the signature server.</p>

<h3>2e. Bug Reports (Owner/Operator Only)</h3>
<p>The bug reporter is disabled by default (<code>bug_reporter_enabled: false</code>). If enabled by a Forge operator, it may file error reports to a private GitHub repository containing: exception type, stack trace (limited to Forge's own code), hardware info, and Forge version. No code, prompts, or file contents are included.</p>

<h2>3. What We Never Collect</h2>
<ul>
  <li>Your source code or file contents</li>
  <li>Your AI prompts or AI-generated responses</li>
  <li>Your name, address, or other personal identifiers (unless you provide them to us directly)</li>
  <li>Browsing history or behavior across other websites</li>
</ul>

<h2>4. Cloud AI Providers (User-Configured)</h2>
<p>Forge supports optional integration with third-party AI providers such as OpenAI and Anthropic. These integrations require you to supply your own API key and are entirely optional — Forge defaults to local AI via Ollama. If you configure a cloud provider, your conversations are sent to that provider under their own privacy policies. Dirt Star has no access to that data. We are not responsible for third-party providers' data practices.</p>

<h2>5. Cookies and Website Analytics</h2>
<p>The Forge website (dirt-star.com/Forge) uses session cookies for account authentication only. We do not use advertising cookies, tracking pixels, or third-party analytics platforms.</p>

<h2>6. Data Retention</h2>
<ul>
  <li><strong>Waitlist emails:</strong> Retained until Forge launches and you are notified, or until you request removal</li>
  <li><strong>License activation records:</strong> Retained for the life of your license</li>
  <li><strong>Telemetry bundles:</strong> Retained for up to 90 days, then deleted</li>
</ul>

<h2>7. Your Rights</h2>
<p>You may request access to, correction of, or deletion of any personal data we hold about you by emailing <a href="mailto:privacy@dirt-star.com">privacy@dirt-star.com</a>. We will respond within 30 days. EU and UK residents have additional rights under GDPR; California residents have additional rights under CCPA. Contact us to exercise any of these rights.</p>

<h2>8. Children</h2>
<p>Forge is not directed at children under 13. We do not knowingly collect data from anyone under 13.</p>

<h2>9. Changes to This Policy</h2>
<p>We will post updates here and note the "Last updated" date above. Continued use of Forge after changes constitutes acceptance.</p>

<h2>10. Contact</h2>
<p><a href="mailto:privacy@dirt-star.com">privacy@dirt-star.com</a></p>

</div>
</main>

<?php require_once __DIR__ . '/includes/footer.php'; ?>
