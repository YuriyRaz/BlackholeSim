export class AccessibilityManager {
  constructor() {
    this._reducedMotion = false;
    this._focusIndicator = null;
    this._setupReducedMotion();
    this._setupFocusIndicators();
    this._setupKeyboardNavigation();
  }

  _setupReducedMotion() {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    this._reducedMotion = mediaQuery.matches;
    
    mediaQuery.addEventListener('change', (e) => {
      this._reducedMotion = e.matches;
      this._onReducedMotionChange();
    });
  }

  _setupFocusIndicators() {
    const style = document.createElement('style');
    style.textContent = `
      *:focus {
        outline: 2px solid #4a9eff;
        outline-offset: 2px;
      }
      
      *:focus:not(:focus-visible) {
        outline: none;
      }
      
      *:focus-visible {
        outline: 2px solid #4a9eff;
        outline-offset: 2px;
      }
    `;
    document.head.appendChild(style);
  }

  _setupKeyboardNavigation() {
    document.addEventListener('keydown', (e) => {
      this._handleKeyboardNavigation(e);
    });
  }

  _handleKeyboardNavigation(e) {
    if (e.key === 'Tab') {
      this._manageTabFocus(e);
    }
    
    if (e.key === 'Escape') {
      this._handleEscape();
    }
    
    if (e.key === ' ' && e.target === document.body) {
      e.preventDefault();
    }
  }

  _manageTabFocus(e) {
    const focusableElements = document.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];
    
    if (e.shiftKey) {
      if (document.activeElement === firstElement) {
        lastElement.focus();
        e.preventDefault();
      }
    } else {
      if (document.activeElement === lastElement) {
        firstElement.focus();
        e.preventDefault();
      }
    }
  }

  _handleEscape() {
    const activeElement = document.activeElement;
    if (activeElement && activeElement !== document.body) {
      activeElement.blur();
    }
  }

  addAriaLabels() {
    const canvas = document.getElementById('viewport');
    if (canvas) {
      canvas.setAttribute('role', 'application');
      canvas.setAttribute('aria-label', 'Black hole simulation. Use mouse to orbit, scroll to zoom, right-click to pan.');
    }
    
    const buttons = document.querySelectorAll('.ui-btn');
    buttons.forEach((btn, index) => {
      if (!btn.getAttribute('aria-label')) {
        const text = btn.textContent.trim();
        btn.setAttribute('aria-label', text || `Button ${index + 1}`);
      }
    });
  }

  addKeyboardShortcuts() {
    const shortcuts = {
      'm': 'Toggle mute',
      '1': 'Select first black hole',
      '2': 'Select second black hole',
      '3': 'Select third black hole',
      'r': 'Reset camera',
      'c': 'Toggle cinematic mode',
      'f': 'Toggle fullscreen',
      'h': 'Toggle help'
    };
    
    const helpText = Object.entries(shortcuts)
      .map(([key, action]) => `${key.toUpperCase()}: ${action}`)
      .join('\n');
    
    const helpElement = document.createElement('div');
    helpElement.style.cssText = `
      position: fixed;
      bottom: 10px;
      right: 10px;
      background: rgba(0, 0, 0, 0.8);
      color: #fff;
      padding: 10px;
      border-radius: 4px;
      font-family: monospace;
      font-size: 11px;
      display: none;
      white-space: pre-line;
      z-index: 1000;
    `;
    helpElement.textContent = helpText;
    helpElement.id = 'keyboard-help';
    document.body.appendChild(helpElement);
    
    document.addEventListener('keydown', (e) => {
      if (e.key === 'h' && !e.ctrlKey && !e.altKey && !e.metaKey) {
        const help = document.getElementById('keyboard-help');
        if (help) {
          help.style.display = help.style.display === 'none' ? 'block' : 'none';
        }
      }
    });
  }

  setReducedMotion(enabled) {
    this._reducedMotion = enabled;
    this._onReducedMotionChange();
  }

  _onReducedMotionChange() {
    const event = new CustomEvent('reducedmotionchange', {
      detail: { reduced: this._reducedMotion }
    });
    window.dispatchEvent(event);
  }

  get reducedMotion() {
    return this._reducedMotion;
  }

  announceToScreenReader(message) {
    const announcement = document.createElement('div');
    announcement.setAttribute('role', 'status');
    announcement.setAttribute('aria-live', 'polite');
    announcement.setAttribute('aria-atomic', 'true');
    announcement.style.cssText = `
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    `;
    announcement.textContent = message;
    document.body.appendChild(announcement);
    
    setTimeout(() => {
      announcement.remove();
    }, 1000);
  }

  destroy() {
    const help = document.getElementById('keyboard-help');
    if (help) help.remove();
  }
}