/**
 * g360-signature v1.1.0
 * Web component para branding G360 - Sin Shadow DOM
 */

const G360_SIGNATURE_CSS = `
.g360-signature {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 18px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1;
  opacity: 0.4;
  transition: opacity 0.3s ease;
  cursor: default;
  --g360-green: #00d084;
  --g360-gray: #64748b;
}
.g360-signature:hover {
  opacity: 1;
}
.g360-signature .g360-iw {
  display: flex;
  align-items: center;
  gap: 1px;
  height: 100%;
}
.g360-signature .g360-iso {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  height: 100%;
}
.g360-signature .g360-d {
  width: 4px;
  height: 4px;
  border-radius: 50%;
}
.g360-signature .g360-dt { background: var(--g360-gray); }
.g360-signature .g360-dm { background: var(--g360-green); }
.g360-signature .g360-db { background: var(--g360-gray); }
.g360-signature .g360-ch {
  color: var(--g360-green);
  width: 20px;
  height: 20px;
}
.g360-signature .g360-t {
  color: var(--g360-gray);
  letter-spacing: 0.5px;
}
.g360-signature .g360-v {
  color: var(--g360-gray);
  opacity: 0.7;
}
.g360-signature .g360-s {
  color: var(--g360-gray);
  opacity: 0.5;
}
@media (prefers-color-scheme: dark) {
  .g360-signature { --g360-gray: #94a3b8; }
}
`;

class G360Signature extends HTMLElement {
  static get observedAttributes() {
    return ['mode', 'version'];
  }

  constructor() {
    super();
  }

  connectedCallback() {
    this._injectStyles();
    this.render();
  }

  attributeChangedCallback() {
    this.render();
  }

  _injectStyles() {
    if (document.getElementById('g360-signature-css')) return;
    const style = document.createElement('style');
    style.id = 'g360-signature-css';
    style.textContent = G360_SIGNATURE_CSS;
    document.head.appendChild(style);
  }

  get mode() {
    return this.getAttribute('mode') || 'own';
  }

  get version() {
    return this.getAttribute('version') || '';
  }

  render() {
    const isOwn = this.mode === 'own';
    const mainText = isOwn ? 'G360 by ccusi' : 'powered by G360';

    const versionHtml = this.version
      ? `<span class="g360-s">&gt;</span><span class="g360-v">${this.version}</span>`
      : '';

    this.innerHTML = `
      <span class="g360-signature">
        <span class="g360-iw">
          <span class="g360-iso">
            <span class="g360-d g360-dt"></span>
            <span class="g360-d g360-dm"></span>
            <span class="g360-d g360-db"></span>
          </span>
          <svg class="g360-ch" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="6 4 14 10 6 16"></polyline>
          </svg>
        </span>
        <span class="g360-t">${mainText}</span>
        ${versionHtml}
      </span>
    `;
  }
}

if (!customElements.get('g360-signature')) {
  customElements.define('g360-signature', G360Signature);
}
