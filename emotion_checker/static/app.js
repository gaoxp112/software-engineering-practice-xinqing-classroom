const navButton = document.querySelector('[data-nav-toggle]');
const nav = document.querySelector('[data-nav]');
if (navButton && nav) {
  navButton.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    navButton.setAttribute('aria-expanded', String(open));
  });
}

document.querySelectorAll('[data-dismiss]').forEach((button) => {
  button.addEventListener('click', () => button.parentElement.remove());
});

document.querySelectorAll('[data-password-toggle]').forEach((button) => {
  button.addEventListener('click', () => {
    const input = button.closest('.password-input').querySelector('input');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    button.textContent = show ? '隐藏' : '显示';
    button.setAttribute('aria-label', show ? '隐藏密码' : '显示密码');
    button.setAttribute('aria-pressed', String(show));
  });
});

document.querySelectorAll('[data-modal-open]').forEach((button) => {
  button.addEventListener('click', () => {
    const modal = document.querySelector(`[data-modal="${button.dataset.modalOpen}"]`);
    if (modal) {
      modal.hidden = false;
      modal.querySelector('input:not([type="hidden"])')?.focus();
    }
  });
});

document.querySelectorAll('[data-modal-close]').forEach((button) => {
  button.addEventListener('click', () => { button.closest('[data-modal]').hidden = true; });
});

document.querySelectorAll('[data-modal]').forEach((modal) => {
  modal.addEventListener('click', (event) => {
    if (event.target === modal) modal.hidden = true;
  });
});

const textarea = document.querySelector('textarea[maxlength]');
if (textarea) {
  const counter = textarea.parentElement.querySelector('.char-count');
  const update = () => { if (counter) counter.textContent = `${textarea.value.length} / ${textarea.maxLength}`; };
  textarea.addEventListener('input', update);
  update();
}

const moodChartColors = ['#e86f51', '#1d7a6e', '#f2c14e', '#6c7bd9', '#b05b8d', '#5d9c76'];

const setupCanvas = (canvas) => {
  const box = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(box.width * ratio);
  canvas.height = Math.round(box.height * ratio);
  const context = canvas.getContext('2d');
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width: box.width, height: box.height };
};

const chartDataElement = document.querySelector('#chart-data');
if (chartDataElement) {
  const data = JSON.parse(chartDataElement.textContent);
  const colors = moodChartColors;

  const drawDonut = (canvas) => {
    const { context, width, height } = setupCanvas(canvas);
    const total = data.counts.reduce((sum, value) => sum + value, 0);
    const radius = Math.min(width * .24, height * .35);
    const cx = width < 420 ? width / 2 : width * .32;
    const cy = height / 2;
    let angle = -Math.PI / 2;
    data.counts.forEach((value, index) => {
      if (!value) return;
      const next = angle + (value / total) * Math.PI * 2;
      context.beginPath();
      context.arc(cx, cy, radius, angle, next);
      context.arc(cx, cy, radius * .58, next, angle, true);
      context.closePath();
      context.fillStyle = colors[index];
      context.fill();
      angle = next;
    });
    context.fillStyle = '#17211e';
    context.textAlign = 'center';
    context.font = '700 24px system-ui';
    context.fillText(String(total), cx, cy + 2);
    context.fillStyle = '#66726e';
    context.font = '12px system-ui';
    context.fillText('次反馈', cx, cy + 22);
    if (width >= 420) {
      const present = data.keys.filter((key, index) => data.counts[index] > 0);
      const rowHeight = Math.min(28, (height - 32) / present.length);
      present.forEach((key, row) => {
        const index = data.keys.indexOf(key);
        const x = width * .62;
        const y = 22 + row * rowHeight;
        context.fillStyle = colors[index];
        context.fillRect(x, y - 9, 12, 12);
        context.fillStyle = '#4f5b57';
        context.textAlign = 'left';
        context.font = '13px system-ui';
        const percent = total ? Math.round(data.counts[index] * 100 / total) : 0;
        context.fillText(`${data.labels[index]}  ${percent}%`, x + 20, y + 1);
      });
    }
  };

  const drawTrend = (canvas) => {
    const { context, width, height } = setupCanvas(canvas);
    const keys = data.keys.filter((key) => data.trend[key].some((value) => value > 0));
    const max = Math.max(1, ...keys.flatMap((key) => data.trend[key]));
    const detailedTimeLabels = data.trendLabels[0].length > 5;
    const left = 44, right = detailedTimeLabels ? 44 : 22, bottom = 42;
    const plotWidth = width - left - right;
    const legendColumns = Math.max(1, Math.floor(plotWidth / 64));
    const top = Math.max(24, 8 + Math.ceil(keys.length / legendColumns) * 16);
    const plotHeight = height - top - bottom;
    context.strokeStyle = '#dbe2df';
    context.lineWidth = 1;
    for (let row = 0; row <= 4; row += 1) {
      const y = top + plotHeight * row / 4;
      context.beginPath(); context.moveTo(left, y); context.lineTo(width - right, y); context.stroke();
    }
    keys.forEach((key) => {
      const color = colors[data.keys.indexOf(key)];
      context.beginPath();
      data.trend[key].forEach((value, index) => {
        const x = left + plotWidth * index / 11;
        const y = top + plotHeight - value / max * plotHeight;
        if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
      });
      context.strokeStyle = color;
      context.lineWidth = 2;
      context.stroke();
      data.trend[key].forEach((value, index) => {
        const x = left + plotWidth * index / 11;
        const y = top + plotHeight - value / max * plotHeight;
        context.beginPath();
        context.arc(x, y, 3, 0, Math.PI * 2);
        context.fillStyle = '#fff';
        context.fill();
        context.strokeStyle = color;
        context.lineWidth = 1.5;
        context.stroke();
      });
    });
    drawTimeLabels(context, data.trendLabels, (index) => left + plotWidth * index / 11, height - 17, plotWidth,
                   detailedTimeLabels ? 76 : 54);
    keys.forEach((key, position) => {
      const index = data.keys.indexOf(key);
      const x = left + (position % legendColumns) * Math.min(82, plotWidth / legendColumns);
      const y = 3 + Math.floor(position / legendColumns) * 16;
      context.fillStyle = colors[index];
      context.fillRect(x, y, 9, 9);
      context.fillStyle = '#66726e';
      context.textAlign = 'left';
      context.fillText(data.labels[index], x + 13, y + 8);
    });
  };

  const renderCharts = () => {
    document.querySelectorAll('[data-chart="donut"]').forEach(drawDonut);
    document.querySelectorAll('[data-chart="trend"]').forEach(drawTrend);
  };
  renderCharts();
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderCharts, 120);
  });
}

function drawTimeLabels(context, labels, xAt, y, plotWidth, labelSpacing) {
  const count = Math.min(labels.length, Math.max(2, Math.floor(plotWidth / labelSpacing)));
  context.fillStyle = '#66726e';
  context.font = '11px system-ui';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  let previousLabel;
  for (let tick = 0; tick < count; tick += 1) {
    const index = Math.round(tick * (labels.length - 1) / Math.max(1, count - 1));
    const label = labels[index];
    if (label === previousLabel) continue;
    context.fillText(label, xAt(index), y);
    previousLabel = label;
  }
}

const drawClassroomTrend = (canvas, timeline, keys) => {
  const { context, width, height } = setupCanvas(canvas);
  const left = 32, right = 12, top = 12, bottom = height - 30;
  const plotWidth = width - left - right;
  const slotWidth = plotWidth / timeline.labels.length;
  const xAt = (index) => left + (index + .5) * slotWidth;
  const totals = timeline.labels.map((_, index) => keys.reduce((sum, mood) => sum + timeline.series[mood][index], 0));
  const peak = Math.max(1, ...totals);
  const ticks = Math.min(4, peak);
  const step = Math.ceil(peak / ticks);
  const pixelsPerRecord = (bottom - top) / (ticks * step);

  context.font = '11px system-ui';
  context.textAlign = 'right';
  context.textBaseline = 'middle';
  context.strokeStyle = '#dbe2df';
  context.fillStyle = '#66726e';
  for (let tick = 0; tick <= ticks; tick += 1) {
    const value = tick * step;
    const y = bottom - value * pixelsPerRecord;
    context.beginPath();
    context.moveTo(left, y);
    context.lineTo(width - right, y);
    context.stroke();
    context.fillText(String(value), left - 7, y);
  }
  const barWidth = Math.min(40, slotWidth * .72);
  timeline.labels.forEach((_, index) => {
    let y = bottom;
    keys.forEach((mood, colorIndex) => {
      const barHeight = timeline.series[mood][index] * pixelsPerRecord;
      y -= barHeight;
      context.fillStyle = moodChartColors[colorIndex];
      context.fillRect(xAt(index) - barWidth / 2, y, barWidth, barHeight);
    });
  });
  drawTimeLabels(context, timeline.labels, xAt, bottom + 16, plotWidth, 44);
  if (!timeline.total) context.fillText('此时段暂无课堂反馈', width / 2, height / 2);
};

const studentTrendData = document.querySelector('#student-trend-data');
if (studentTrendData) {
  const data = JSON.parse(studentTrendData.textContent);
  const canvas = document.querySelector('[data-student-trend]');
  const drawStudentTrend = () => {
    const { context, width, height } = setupCanvas(canvas);
    const left = 55, right = 46, top = 14, bottom = height - 34;
    const plotWidth = width - left - right;
    const xAt = (index) => left + plotWidth * (data.records.length === 1 ? .5 : index / (data.records.length - 1));
    const yAt = (index) => top + (bottom - top) * index / (data.labels.length - 1);

    context.strokeStyle = '#dbe2df';
    context.fillStyle = '#52625a';
    context.font = '12px system-ui';
    context.textAlign = 'right';
    context.textBaseline = 'middle';
    data.labels.forEach((label, index) => {
      const y = yAt(index);
      context.beginPath();
      context.moveTo(left, y);
      context.lineTo(width - right, y);
      context.stroke();
      context.fillText(label, left - 10, y);
    });
    const points = data.records.map((record, index) => ({ x: xAt(index), mood: data.keys.indexOf(record.mood) }));
    context.beginPath();
    points.forEach(({ x, mood }, index) => {
      if (index === 0) context.moveTo(x, yAt(mood));
      else context.lineTo(x, yAt(mood));
    });
    context.strokeStyle = '#839a91';
    context.lineWidth = 1.5;
    context.stroke();
    points.forEach(({ x, mood }) => {
      context.beginPath();
      context.arc(x, yAt(mood), 4.5, 0, Math.PI * 2);
      context.fillStyle = moodChartColors[mood];
      context.fill();
    });
    drawTimeLabels(context, data.records.map((record) => record.time), xAt, bottom + 17, plotWidth, 88);
  };
  drawStudentTrend();
  window.addEventListener('resize', drawStudentTrend);
}

const teacherDataElement = document.querySelector('#teacher-chart-data');
if (teacherDataElement) {
  const config = JSON.parse(teacherDataElement.textContent);
  const moodKeys = config.keys;
  const summaryInterval = 3000;
  const summaryNote = document.querySelector('.detail-grid .panel-note');
  if (summaryNote) summaryNote.textContent = `约每 ${summaryInterval / 1000} 秒更新`;
  const classroomCanvas = document.querySelector('[data-class-trend]');
  const trendRange = document.querySelector('[data-class-trend-range]');
  const advicePanel = document.querySelector('[data-teaching-advice]');
  let classroomTimeline = config.timeline;
  const renderClassroomTrend = () => {
    if (!classroomCanvas || !classroomTimeline) return;
    trendRange.textContent = classroomTimeline.range;
    drawClassroomTrend(classroomCanvas, classroomTimeline, moodKeys);
  };
  document.querySelectorAll('.mood-chart-legend span').forEach((item, index) => {
    item.style.setProperty('--mood-color', moodChartColors[index]);
  });
  renderClassroomTrend();
  window.addEventListener('resize', renderClassroomTrend);

  const refreshSummary = async () => {
    try {
      const response = await fetch(config.url, { cache: 'no-store', headers: { Accept: 'application/json' } });
      if (!response.ok) return;
      const summary = await response.json();
      classroomTimeline = summary.timeline;
      renderClassroomTrend();
      if (advicePanel && summary.advice) {
        const advice = summary.advice;
        advicePanel.dataset.state = advice.state;
        advicePanel.querySelector('[data-advice-title]').textContent = advice.title;
        advicePanel.querySelector('[data-advice-detail]').textContent = advice.detail;
        advicePanel.querySelector('[data-advice-counts]').textContent = `共 ${advice.total} 条 · 开心和平静 ${advice.positive} 条 · 关注信号 ${advice.attention} 条`;
      }
      document.querySelector('[data-total]').textContent = summary.total;
      document.querySelector('[data-positive-rate]').textContent = summary.positive_rate;
      document.querySelector('[data-participants]').textContent = summary.participants;
      moodKeys.forEach((key) => {
        document.querySelector(`[data-mood-count="${key}"]`).textContent = summary.counts[key];
        document.querySelector(`[data-mood-bar="${key}"]`).style.width = summary.total
          ? `${summary.counts[key] * 100 / summary.total}%` : '0%';
      });
      const feed = document.querySelector('[data-live-feed]');
      feed.replaceChildren();
      if (!summary.recent.length) {
        const empty = document.createElement('p');
        empty.className = 'muted';
        empty.textContent = '还没有反馈。';
        feed.append(empty);
        return;
      }
      summary.recent.forEach((row) => {
        const moodIndex = moodKeys.indexOf(row.mood);
        const item = document.createElement('div');
        item.className = 'feed-item';
        const orb = document.createElement('span');
        orb.className = 'mood-orb small';
        orb.textContent = config.emojis[moodIndex];
        const copy = document.createElement('div');
        const author = document.createElement('strong');
        author.textContent = row.participant;
        const note = document.createElement('p');
        note.textContent = `${config.labels[moodIndex]}${row.note ? ` · ${row.note}` : ''}`;
        copy.append(author, note);
        const time = document.createElement('time');
        time.textContent = row.created_at.slice(11, 16);
        item.append(orb, copy, time);
        feed.append(item);
      });
    } catch (_error) {
      // Keep the last known classroom summary when a refresh fails.
    }
  };

  const cameraPanel = document.querySelector('[data-camera-url]');
  const status = cameraPanel?.querySelector('[data-camera-status]');
  const result = cameraPanel?.querySelector('[data-camera-result]');
  const count = cameraPanel?.querySelector('[data-camera-count]');
  const start = cameraPanel?.querySelector('[value="start"]');
  const stop = cameraPanel?.querySelector('[value="stop"]');
  const preview = cameraPanel?.querySelector('[data-camera-preview-url]');
  const previewContext = preview?.getContext('2d');
  let previewRunning = false;

  const drawCameraFrame = (frame, detection) => {
    if (preview.width !== frame.width || preview.height !== frame.height) {
      preview.width = frame.width;
      preview.height = frame.height;
    }
    previewContext.drawImage(frame, 0, 0);
    if (!detection.box) return;

    const [x, y, width, height] = detection.box;
    const index = moodKeys.indexOf(detection.mood);
    const label = index === -1 ? '已检测到人脸' : `${config.labels[index]}  ${Math.round(detection.confidence * 100)}%`;
    const fontSize = Math.max(18, Math.round(preview.width * .036));
    previewContext.lineWidth = 3;
    previewContext.strokeStyle = '#62f0ad';
    previewContext.strokeRect(x, y, width, height);
    previewContext.font = `600 ${fontSize}px system-ui, sans-serif`;
    previewContext.textBaseline = 'middle';
    const badgeWidth = Math.ceil(previewContext.measureText(label).width) + 20;
    const badgeHeight = fontSize + 12;
    const badgeX = Math.max(0, Math.min(x, preview.width - badgeWidth));
    const badgeY = Math.max(0, Math.min(y - badgeHeight, preview.height - badgeHeight));
    previewContext.fillStyle = '#12291e';
    previewContext.fillRect(badgeX, badgeY, badgeWidth, badgeHeight);
    previewContext.fillStyle = '#fff';
    previewContext.fillText(label, badgeX + 10, badgeY + badgeHeight / 2);
  };

  const refreshPreview = async () => {
    try {
      if (!previewRunning) return;
      const response = await fetch(preview.dataset.cameraPreviewUrl, { cache: 'no-store' });
      if (response.status !== 200 || response.redirected) return;
      const detection = JSON.parse(response.headers.get('X-Camera-Detection'));
      const frame = await createImageBitmap(await response.blob());
      try {
        if (!previewRunning) return;
        drawCameraFrame(frame, detection);
        preview.hidden = false;
      } finally {
        frame.close();
      }
    } catch (_error) {
      // The next poll can use a new frame after a transient capture failure.
    } finally {
      window.setTimeout(refreshPreview, previewRunning ? 100 : 500);
    }
  };

  const refreshCamera = async () => {
    if (!cameraPanel) return false;
    try {
      const response = await fetch(cameraPanel.dataset.cameraUrl, { cache: 'no-store' });
      if (!response.ok) return false;
      const camera = await response.json();
      const running = ['starting', 'running'].includes(camera.state);
      previewRunning = camera.is_open && camera.state === 'running';
      if (previewContext && !previewRunning && !preview.hidden) {
        previewContext.clearRect(0, 0, preview.width, preview.height);
        preview.hidden = true;
      }
      status.textContent = camera.is_open ? camera.message : '课堂已结束';
      start.disabled = !camera.is_open || running || camera.state === 'stopping';
      stop.disabled = !running;
      const samplesChanged = camera.saved_count !== Number(count.textContent);
      count.textContent = camera.saved_count;
      const latest = camera.latest;
      if (latest?.mood) {
        const percent = Math.round(latest.confidence * 100);
        result.textContent = `${latest.time} · ${latest.mood.emoji} ${latest.mood.label} · 置信度 ${percent}% · ${latest.saved ? '已入库' : '仅显示'}`;
      } else if (running) {
        result.textContent = '请面向摄像头，等待下一次采样。';
      } else {
        result.textContent = '点击开始后，面向摄像头即可查看识别结果。';
      }
      return samplesChanged;
    } catch (_error) {
      status.textContent = '正在重新连接课堂服务…';
      return false;
    }
  };

  let lastSummaryRefresh = performance.now();
  const refreshDashboard = async () => {
    const samplesChanged = await refreshCamera();
    const now = performance.now();
    if (samplesChanged || now - lastSummaryRefresh >= summaryInterval) {
      lastSummaryRefresh = now;
      await refreshSummary();
    }
    window.setTimeout(refreshDashboard, cameraPanel ? 1000 : summaryInterval);
  };
  refreshDashboard();
  if (previewContext) refreshPreview();
}
