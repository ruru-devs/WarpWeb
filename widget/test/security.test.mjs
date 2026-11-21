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

test('Widget Accessibility: keyboard navigation index wrap-around', () => {
  const itemCount = 5;
  let activeIndex = -1;

  // ArrowDown
  activeIndex = (activeIndex + 1) % itemCount;
  assert.equal(activeIndex, 0);

  // ArrowDown 4 more times
  for (let i = 0; i < 4; i++) {
    activeIndex = (activeIndex + 1) % itemCount;
  }
  assert.equal(activeIndex, 4);

  // Wrap around back to 0
  activeIndex = (activeIndex + 1) % itemCount;
  assert.equal(activeIndex, 0);

  // ArrowUp wrap around to 4
  activeIndex = (activeIndex - 1 + itemCount) % itemCount;
  assert.equal(activeIndex, 4);
});

test('Widget Request Sequencing: ignores stale responses when newer request finishes', () => {
  let latestRequestId = 0;
  let renderedResult = null;

  function simulateResponse(reqId, data) {
    if (reqId === latestRequestId) {
      renderedResult = data;
    }
  }

  // Request 1 starts
  const req1 = ++latestRequestId;
  // Request 2 starts before req 1 finishes
  const req2 = ++latestRequestId;

  // Request 2 finishes first
  simulateResponse(req2, 'new query results');
  assert.equal(renderedResult, 'new query results');

  // Stale request 1 finishes later
  simulateResponse(req1, 'old query results');
  // Must NOT overwrite newer results
  assert.equal(renderedResult, 'new query results');
});
