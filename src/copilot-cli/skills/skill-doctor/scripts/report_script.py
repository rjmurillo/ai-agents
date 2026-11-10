"""Browser interaction script for the self-contained skill report."""


def page_script(card_data: str, clamp_px: int) -> str:
    """Diff collapsing plus a canvas-drawn 1200x675 share image."""
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
      button.textContent = collapsed ? 'show less' : 'show more';
      if (!collapsed) wrap.scrollIntoView({ block: 'nearest' });
    });
    syncToggle(wrap, button);
    if (window.ResizeObserver) {
      new ResizeObserver(function () { syncToggle(wrap, button); }).observe(view);
    }
  });

  // --- share image -------------------------------------------------------
  var MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  var FG = '#1a1522', MUTED = '#5d5966', MUTED2 = '#918d9a', ACCENT = '#2a1eff';
  var LINE = 'rgba(13,10,61,0.16)', LINE_SOFT = 'rgba(13,10,61,0.07)';
  var PANEL = '#f6f5fb';
  var W = 1200, H = 675;

  function drawMark(c, x, y, size) {
    var scale = size / CARD.viewbox[0];
    c.save();
    c.translate(x, y);
    c.scale(scale, scale);
    CARD.paths.forEach(function (path) {
      c.fillStyle = path.fill;
      c.fill(new Path2D(path.d), 'evenodd');
    });
    c.restore();
  }

  function drawCard(scale) {
    var canvas = document.createElement('canvas');
    canvas.width = W * scale;
    canvas.height = H * scale;
    var c = canvas.getContext('2d');
    c.scale(scale, scale);

    function font(weight, size) { c.font = weight + ' ' + size + 'px ' + MONO; }
    function track(value) { try { c.letterSpacing = value; } catch (e) {} }
    function rule(x, y, w, h) { c.fillStyle = LINE; c.fillRect(x, y, w, h); }
    function text(str, x, y, align) {
      c.textAlign = align || 'left';
      c.textBaseline = 'middle';
      c.fillText(str, x, y);
      c.textAlign = 'left';
    }
    function dots(x, y, w, h, step) {
      c.save();
      c.beginPath();
      c.rect(x, y, w, h);
      c.clip();
      c.fillStyle = LINE_SOFT;
      for (var i = x; i < x + w; i += step) {
        for (var j = y; j < y + h; j += step) {
          c.beginPath();
          c.arc(i + 1, j + 1, 1, 0, Math.PI * 2);
          c.fill();
        }
      }
      c.restore();
    }

    c.fillStyle = '#fff';
    c.fillRect(0, 0, W, H);
    dots(0, 0, W, H, 22);

    var fx = 48, fy = 40, fw = 1104, fh = 595;
    c.fillStyle = '#fff';
    c.fillRect(fx, fy, fw, fh);
    rule(fx, fy, fw, 1);
    rule(fx, fy + fh - 1, fw, 1);
    rule(fx, fy, 1, fh);
    rule(fx + fw - 1, fy, 1, fh);

    // meta bar
    var barBottom = fy + 38;
    rule(fx, barBottom, fw, 1);
    font('400', 11);
    track('1.1px');
    c.fillStyle = MUTED2;
    var handle = CARD.handle.toUpperCase();
    text(handle, fx + 16, fy + 19);
    var handleEnd = fx + 16 + c.measureText(handle).width + 14;
    var harness = CARD.harness.toUpperCase();
    var harnessW = c.measureText(harness).width + 12;
    var harnessX = fx + fw - 16 - harnessW;
    c.strokeStyle = LINE;
    c.lineWidth = 1;
    c.strokeRect(harnessX + 0.5, fy + 8.5, harnessW - 1, 21);
    text(harness, harnessX + 6, fy + 19);
    var meta = CARD.meta.toUpperCase();
    var metaX = harnessX - 14 - c.measureText(meta).width;
    text(meta, metaX, fy + 19);
    rule(handleEnd, fy + 19, Math.max(0, metaX - 14 - handleEnd), 1);
    track('normal');

    // body
    dots(fx + 1, barBottom + 1, fw - 2, 404, 26);
    font('400', 11);
    track('0.4px');
    c.fillStyle = ACCENT;
    text('# ' + CARD.eyebrow, fx + 36, barBottom + 18);
    font('500', 34);
    track('-2px');
    c.fillStyle = FG;
    text(CARD.title, fx + 36, barBottom + 52);
    track('normal');

    var mainMid = barBottom + 74 + (405 - 74) / 2;

    font('600', 170);
    track('-8px');
    c.fillStyle = ACCENT;
    text(CARD.grade, fx + 186, mainMid - 15, 'center');
    track('normal');
    font('400', 11);
    track('1.5px');
    c.fillStyle = MUTED2;
    text(CARD.grade_label.toUpperCase(), fx + 186, mainMid + 88, 'center');
    track('normal');

    var bx = fx + 392;
    var bw = fx + fw - 36 - bx;
    var rowH = 35, gap = CARD.bars.length > 3 ? 12 : 28;
    var top = mainMid - (CARD.bars.length * rowH + (CARD.bars.length - 1) * gap) / 2;
    CARD.bars.forEach(function (bar, index) {
      var y = top + index * (rowH + gap);
      font('500', 14);
      c.fillStyle = FG;
      text(bar[0].toLowerCase(), bx, y + 9);
      font('600', 14);
      text(String(bar[1]), bx + bw, y + 9, 'right');
      c.fillStyle = LINE_SOFT;
      c.fillRect(bx, y + 27, bw, 8);
      c.strokeStyle = LINE;
      c.strokeRect(bx + 0.5, y + 27.5, bw - 1, 7);
      c.fillStyle = ACCENT;
      c.fillRect(bx, y + 27, bw * Math.max(0, Math.min(100, bar[1])) / 100, 8);
    });

    // stats
    var sy = barBottom + 405;
    c.fillStyle = PANEL;
    c.fillRect(fx + 1, sy, fw - 2, 96);
    rule(fx, sy, fw, 1);
    var colW = (fw - 2) / 3;
    CARD.stats.forEach(function (stat, index) {
      var cx = fx + 1 + index * colW;
      if (index) rule(cx, sy, 1, 96);
      font('600', 40);
      c.fillStyle = FG;
      text(stat[0], cx + 24, sy + 40);
      font('400', 12);
      c.fillStyle = MUTED;
      text(stat[1], cx + 24, sy + 72);
    });

    // footer
    var gy = sy + 96;
    c.fillStyle = '#fff';
    c.fillRect(fx + 1, gy, fw - 2, fy + fh - gy - 1);
    rule(fx, gy, fw, 1);
    drawMark(c, fx + 16, gy + 15, 27);
    font('600', 15);
    track('-0.45px');
    c.fillStyle = FG;
    text(CARD.stamp[0], fx + 54, gy + 20);
    track('normal');
    font('400', 11);
    c.fillStyle = MUTED2;
    text(CARD.stamp[1], fx + 54, gy + 37);

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
        button.textContent = 'saved \u2713';
        setTimeout(function () { button.textContent = label; }, 2000);
      }, 'image/png');
    });
  });
})();
"""
    return script.replace("__CARD__", card_data.replace("</", "<\\/")).replace(
        "__CLAMP__", str(clamp_px)
    )
