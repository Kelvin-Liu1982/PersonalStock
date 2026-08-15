// quote-refresh.js — 行情快照条「刷新行情」按钮通用逻辑
// 用法：在看板页 <head> 里加 <script src="../quote-refresh.js" defer></script>，
//      并在按钮上放 data-refresh-mode="rebuild|message" 等配置。

(function () {
  function setupRefresh() {
    const btn = document.getElementById('qRefreshBtn');
    const msg = document.getElementById('qRefreshMsg');
    if (!btn) return;

    const spinner = btn.querySelector('.spinner');
    const label = btn.querySelector('.lbl');

    // 默认 message 模式：仅提示用户本地运行构建脚本
    const mode = btn.dataset.refreshMode || 'message';
    const endpoint = btn.dataset.refreshEndpoint || '/rebuild';
    const infoMsg =
      btn.dataset.refreshMessage ||
      '行情为静态快照，实时刷新请本地运行构建脚本后重新生成看板。';

    const setLoading = (loading) => {
      btn.disabled = loading;
      if (spinner) spinner.classList.toggle('hidden', !loading);
      if (label && loading) label.textContent = mode === 'rebuild' ? '刷新中…' : '检查中…';
      // 非加载状态不恢复 label：rebuild 错误时会保留“重试”，message 模式由各自分支恢复
    };

    btn.addEventListener('click', () => {
      setLoading(true);
      if (msg) {
        msg.className = 'qmsg';
        msg.textContent = '';
      }

      if (mode === 'rebuild') {
        const t0 = Date.now();
        fetch(endpoint, { cache: 'no-store' })
          .then(async (r) => {
            const dt = ((Date.now() - t0) / 1000).toFixed(1);
            let o = null;
            try {
              o = await r.json();
            } catch (e) {
              // 响应不是 JSON（例如线上 404 HTML/空 body）
            }
            if (r.ok && o && o.ok) {
              if (msg) {
                msg.className = 'qmsg ok';
                msg.textContent = '✓ ' + o.msg + '（' + dt + 's）';
              }
              setTimeout(() => location.reload(), 800);
            } else if (o && o.msg) {
              // 本地 rebuild 服务端返回了明确的错误 JSON
              if (msg) {
                msg.className = 'qmsg err';
                msg.textContent = '✗ ' + o.msg;
              }
              if (label) label.textContent = '重试';
            } else {
              // 非 JSON 或非 OK 响应：线上不存在 /rebuild，降级为静态快照提示
              if (msg) {
                msg.className = 'qmsg';
                msg.textContent = infoMsg;
              }
              if (label) label.textContent = '刷新行情';
            }
          })
          .catch((e) => {
            if (msg) {
              msg.className = 'qmsg err';
              msg.textContent = '✗ ' + e;
            }
            if (label) label.textContent = '重试';
          })
          .finally(() => {
            btn.disabled = false;
            if (spinner) spinner.classList.add('hidden');
          });
      } else {
        setTimeout(() => {
          if (msg) {
            msg.className = 'qmsg';
            msg.textContent = infoMsg;
          }
          setLoading(false);
          if (label) label.textContent = '刷新行情';
        }, 600);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupRefresh);
  } else {
    setupRefresh();
  }
})();
