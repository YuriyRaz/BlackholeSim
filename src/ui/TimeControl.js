export class TimeControl {
  constructor(physicsEngine) {
    this.physics = physicsEngine;
    this._el = null;
    this._timeDisplay = null;
    this._speedButtons = {};
    this._playPauseBtn = null;
    this._scrubber = null;
    this._scrubbing = false;
    this._wasPlayingBeforeScrub = false;
  }

  mount(container) {
    this._el = document.createElement('div');
    this._el.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
        <button class="ui-btn" id="play-pause-btn">⏸</button>
        <div style="display:flex;gap:2px;" id="speed-buttons">
          <button class="ui-btn speed-btn" data-speed="0.1">0.1×</button>
          <button class="ui-btn speed-btn" data-speed="0.25">0.25×</button>
          <button class="ui-btn speed-btn" data-speed="0.5">0.5×</button>
          <button class="ui-btn speed-btn active" data-speed="1">1×</button>
          <button class="ui-btn speed-btn" data-speed="2">2×</button>
          <button class="ui-btn speed-btn" data-speed="5">5×</button>
          <button class="ui-btn speed-btn" data-speed="10">10×</button>
        </div>
        <span class="ui-label" id="sim-time">t = 0.00s</span>
        <input type="range" id="timeline-scrubber" min="0" max="1000" value="0" style="flex:1;min-width:100px;">
        <button class="ui-btn" id="reset-btn">↺ Reset</button>
      </div>
    `;
    container.appendChild(this._el);

    this._playPauseBtn = this._el.querySelector('#play-pause-btn');
    this._timeDisplay = this._el.querySelector('#sim-time');
    this._scrubber = this._el.querySelector('#timeline-scrubber');

    this._playPauseBtn.addEventListener('click', () => this._togglePlayPause());
    this._el.querySelector('#reset-btn').addEventListener('click', () => this._reset());

    this._el.querySelectorAll('.speed-btn').forEach(btn => {
      const speed = parseFloat(btn.dataset.speed);
      this._speedButtons[speed] = btn;
      btn.addEventListener('click', () => {
        this.physics.speedMultiplier = speed;
        this._el.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });

    this._scrubber.addEventListener('input', (e) => {
      if (!this._scrubbing) {
        this._wasPlayingBeforeScrub = this.physics.playing;
        this.physics.playing = false;
        this._scrubbing = true;
      }
      const maxTime = this.physics.simTime;
      const targetTime = (e.target.value / 1000) * maxTime;
      this.physics.scrubTo(targetTime);
    });

    this._scrubber.addEventListener('change', () => {
      this._scrubbing = false;
      this.physics.playing = this._wasPlayingBeforeScrub;
    });

    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT') return;
      if (e.code === 'Space') {
        e.preventDefault();
        this._togglePlayPause();
      } else if (e.code === 'BracketLeft') {
        this._changeSpeed(-1);
      } else if (e.code === 'BracketRight') {
        this._changeSpeed(1);
      }
    });
  }

  _togglePlayPause() {
    this.physics.playing = !this.physics.playing;
    this._playPauseBtn.textContent = this.physics.playing ? '⏸' : '▶';
  }

  _reset() {
    this.physics.reset();
    this.physics.playing = true;
    this.physics.speedMultiplier = 1;
    this._playPauseBtn.textContent = '⏸';
    this._el.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
    this._speedButtons[1]?.classList.add('active');
  }

  _changeSpeed(direction) {
    const speeds = [0.1, 0.25, 0.5, 1, 2, 5, 10];
    const current = speeds.indexOf(this.physics.speedMultiplier);
    const next = Math.max(0, Math.min(speeds.length - 1, current + direction));
    this.physics.speedMultiplier = speeds[next];
    this._el.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
    this._speedButtons[speeds[next]]?.classList.add('active');
  }

  update() {
    if (this._timeDisplay) {
      this._timeDisplay.textContent = `t = ${this.physics.simTime.toFixed(2)}s`;
    }
    if (!this._scrubbing && this._scrubber) {
      const maxSnapshots = this.physics.getSnapshots();
      const maxTime = maxSnapshots.length > 0 ? maxSnapshots[maxSnapshots.length - 1].time : this.physics.simTime;
      this._scrubber.max = 1000;
      this._scrubber.value = maxTime > 0 ? (this.physics.simTime / maxTime) * 1000 : 0;
    }
  }
}
