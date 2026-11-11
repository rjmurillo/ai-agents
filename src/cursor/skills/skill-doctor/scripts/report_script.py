"""Browser interaction script for the self-contained skill report."""


def page_script(card_data: str, clamp_px: int) -> str:
    """Diff collapsing, prompt copy buttons, print expansion, and a canvas share image."""
    script = r"""
(function () {
  var CARD = __CARD__;
  var CLAMP = __CLAMP__;

  // --- collapsible diffs -------------------------------------------------
  // scrollHeight is the full content height whether or not the view is
  // currently clamped, so this measures the same either way. Only diffs that
  // actually overflow get clamped, so short ones never pick up the fade.
  function syncToggle(wrap, button) {
    var view = wrap.querySelector('.diff-view');
    if (!view) return;
    var overflowing = view.scrollHeight > CLAMP + 24;
    wrap.dataset.overflowing = overflowing ? 'true' : 'false';
    button.hidden = !overflowing;
  }

  document.querySelectorAll('.diff-wrap').forEach(function (wrap) {
    var button = wrap.querySelector('.diff-toggle');
    var view = wrap.querySelector('.diff-view');
    if (!button || !view) return;
    button.addEventListener('click', function () {
      var collapsed = wrap.dataset.collapsed === 'true';
      wrap.dataset.collapsed = collapsed ? 'false' : 'true';
      button.textContent = collapsed ? 'Show less' : 'Show more';
      if (!collapsed) wrap.scrollIntoView({ block: 'nearest' });
    });
    syncToggle(wrap, button);
    if (window.ResizeObserver) {
      new ResizeObserver(function () { syncToggle(wrap, button); }).observe(view);
    }
  });

  // --- handoff prompts: copy and select all -------------------------------
  function selectNode(node) {
    var details = node.closest('details');
    if (details) details.open = true;
    var range = document.createRange();
    range.selectNodeContents(node);
    var selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }

  function flash(status, message) {
    status.textContent = message;
    setTimeout(function () { status.textContent = ''; }, 3000);
  }

  function copyPrompt(node, status) {
    var text = node.textContent;
    var legacy = function () {
      selectNode(node);
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      flash(status, ok ? 'Copied.' : 'Could not copy. The text is selected; press Ctrl+C.');
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () { flash(status, 'Copied.'); }, legacy);
    } else {
      legacy();
    }
  }

  document.querySelectorAll('.handoff').forEach(function (box) {
    var node = box.querySelector('.prompt');
    var status = box.querySelector('.copy-status');
    var copy = box.querySelector('.copy-btn');
    var all = box.querySelector('.select-btn');
    if (!node || !status) return;
    if (copy) copy.addEventListener('click', function () { copyPrompt(node, status); });
    if (all) all.addEventListener('click', function () {
      selectNode(node);
      flash(status, 'Selected. Press Ctrl+C to copy.');
    });
  });

  // --- print: expand every collapsed section, then restore ----------------
  var reopened = [];
  var unclamped = [];
  window.addEventListener('beforeprint', function () {
    document.querySelectorAll('details:not([open])').forEach(function (d) {
      d.open = true;
      reopened.push(d);
    });
    document.querySelectorAll('.diff-wrap[data-collapsed="true"]').forEach(function (w) {
      w.dataset.collapsed = 'false';
      unclamped.push(w);
    });
  });
  window.addEventListener('afterprint', function () {
    reopened.forEach(function (d) { d.open = false; });
    reopened = [];
    unclamped.forEach(function (w) { w.dataset.collapsed = 'true'; });
    unclamped = [];
  });

  // --- share image -------------------------------------------------------
  var SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
  var FG = '#15181e', MUTED = '#4b5260', ACCENT = '#2a4bd0';
  var LINE = '#c3c9d4', LINE_SOFT = '#e1e5ec', PANEL = '#eef0f4', BG = '#f5f6f8';
  var W = 1200, H = 675;

  function drawCard(scale) {
    var canvas = document.createElement('canvas');
    canvas.width = W * scale;
    canvas.height = H * scale;
    var c = canvas.getContext('2d');
    c.scale(scale, scale);

    function font(weight, size) { c.font = weight + ' ' + size + 'px ' + SANS; }
    function text(str, x, y, align) {
      c.textAlign = align || 'left';
      c.textBaseline = 'middle';
      c.fillText(str, x, y);
      c.textAlign = 'left';
    }
    function fit(str, maxWidth) {
      if (c.measureText(str).width <= maxWidth) return str;
      while (str.length > 1 && c.measureText(str + '…').width > maxWidth) {
        str = str.slice(0, -1);
      }
      return str + '…';
    }

    c.fillStyle = BG;
    c.fillRect(0, 0, W, H);
    var fx = 48, fy = 40, fw = 1104, fh = 595;
    c.fillStyle = '#fff';
    c.fillRect(fx, fy, fw, fh);
    c.strokeStyle = LINE;
    c.lineWidth = 1;
    c.strokeRect(fx + 0.5, fy + 0.5, fw - 1, fh - 1);

    // header: title, then handle, harness and scope
    font('700', 36);
    c.fillStyle = FG;
    text(fit(CARD.title, fw - 72), fx + 36, fy + 50);
    font('400', 16);
    c.fillStyle = MUTED;
    text(fit(CARD.handle + '  ·  ' + CARD.harness + '  ·  ' + CARD.meta, fw - 72),
      fx + 36, fy + 88);

    var bodyTop = fy + 112;
    var mainMid = bodyTop + 150;
    font('700', 170);
    c.fillStyle = ACCENT;
    text(CARD.grade, fx + 186, mainMid - 15, 'center');
    font('400', 16);
    c.fillStyle = MUTED;
    text(CARD.grade_label, fx + 186, mainMid + 88, 'center');

    var bx = fx + 392;
    var bw = fx + fw - 36 - bx;
    var rowH = 35, gap = CARD.bars.length > 3 ? 12 : 28;
    var top = mainMid - (CARD.bars.length * rowH + (CARD.bars.length - 1) * gap) / 2;
    CARD.bars.forEach(function (bar, index) {
      var y = top + index * (rowH + gap);
      font('500', 16);
      c.fillStyle = FG;
      text(bar[0], bx, y + 9);
      font('700', 16);
      text(String(bar[1]), bx + bw, y + 9, 'right');
      c.fillStyle = LINE_SOFT;
      c.fillRect(bx, y + 25, bw, 10);
      c.fillStyle = ACCENT;
      c.fillRect(bx, y + 25, bw * Math.max(0, Math.min(100, bar[1])) / 100, 10);
    });

    // stats band
    var sy = fy + fh - 128;
    c.fillStyle = PANEL;
    c.fillRect(fx + 1, sy, fw - 2, 96);
    var colW = (fw - 2) / CARD.stats.length;
    CARD.stats.forEach(function (stat, index) {
      var cx = fx + 1 + index * colW;
      font('700', 36);
      c.fillStyle = FG;
      text(stat[0], cx + 36, sy + 36);
      font('400', 15);
      c.fillStyle = MUTED;
      text(stat[1], cx + 36, sy + 72);
    });

    // neutral tool label
    font('400', 13);
    c.fillStyle = MUTED;
    text(CARD.eyebrow, fx + 36, fy + fh - 16);

    return canvas;
  }

  function slug(value) {
    return (value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'agent';
  }

  var button = document.getElementById('share-png');
  button.addEventListener('click', function () {
    var label = button.textContent;
    button.disabled = true;
    var ready = (document.fonts && document.fonts.ready) || Promise.resolve();
    ready.then(function () {
      drawCard(2).toBlob(function (blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = slug(CARD.handle) + '-skill-report.png';
        a.click();
        setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
        button.disabled = false;
        button.textContent = 'Saved';
        setTimeout(function () { button.textContent = label; }, 2000);
      }, 'image/png');
    });
  });
})();
"""
    return script.replace("__CARD__", card_data.replace("</", "<\\/")).replace(
        "__CLAMP__", str(clamp_px)
    )
