import test from 'node:test';
import assert from 'node:assert/strict';

// Helper matching widget URL validation logic
function isSafeUrl(rawUrl, base = 'https://example.com') {
  try {
    const parsed = new URL(rawUrl, base);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch (e) {
    return false;
  }
}

test('Widget URL Security: allows valid http and https URLs', () => {
  assert.equal(isSafeUrl('https://example.com/doctors#timings'), true);
  assert.equal(isSafeUrl('http://localhost:3000/products'), true);
  assert.equal(isSafeUrl('/contact#form', 'https://example.com'), true);
  assert.equal(isSafeUrl('relative/path', 'https://example.com'), true);
});

test('Widget URL Security: blocks dangerous protocols (XSS/Open Redirect)', () => {
  assert.equal(isSafeUrl('javascript:alert(1)'), false);
  assert.equal(isSafeUrl('JAVASCRIPT:alert(document.cookie)'), false);
  assert.equal(isSafeUrl('data:text/html,<script>alert(1)</script>'), false);
  assert.equal(isSafeUrl('vbscript:msgbox("test")'), false);
  assert.equal(isSafeUrl('file:///etc/passwd'), false);
});
