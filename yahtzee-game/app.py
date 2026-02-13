#!/usr/bin/env python3
# Yahtzee - Flask + Socket.IO (single file)
# Single-join-per-device edition
from __future__ import annotations
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room
import os
import random, time
from collections import defaultdict

app = Flask(__name__)
app.config['SECRET_KEY'] = 'yahtzee-secret-not-for-prod'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')
PORT = int(os.environ.get("PORT", "5000"))

CATEGORIES = [
    'ones','twos','threes','fours','fives','sixes',
    'three_kind','four_kind','full_house','small_straight','large_straight','yahtzee','chance'
]

class Player:
    def __init__(self, sid: str, name: str, device_id: str):
        self.sid = sid
        self.name = name
        self.device_id = device_id  # NEW: used to prevent multiple joins per device
        self.score = {c: None for c in CATEGORIES}
        self.bonus_yahtzees = 0
        self.joined_at = time.time()

    def upper_sum(self):
        return sum(v for k, v in self.score.items()
                   if k in ['ones','twos','threes','fours','fives','sixes'] and v is not None)

    def lower_sum(self):
        base = sum(v for k, v in self.score.items()
                   if k not in ['ones','twos','threes','fours','fives','sixes'] and v is not None)
        return base + (100 * int(self.bonus_yahtzees))

    def upper_bonus(self):
        return 35 if self.upper_sum() >= 63 else 0

    def total(self):
        return self.upper_sum() + self.upper_bonus() + self.lower_sum()

class Game:
    def __init__(self):
        self.players: list[Player] = []
        self.current_index = 0
        self.dice = [1,1,1,1,1]
        self.held = [False]*5
        self.rolls_left = 3
        self.started = False
        self.room = 'global'

    def current_player(self) -> Player | None:
        if not self.players:
            return None
        return self.players[self.current_index % len(self.players)]

    def next_player_index(self):
        if not self.players:
            self.current_index = 0
            return
        self.current_index = (self.current_index + 1) % len(self.players)

    def reset_turn(self):
        self.dice = [1,1,1,1,1]
        self.held = [False]*5
        self.rolls_left = 3

    def roll(self):
        if self.rolls_left <= 0:
            return
        for i in range(5):
            if not self.held[i]:
                self.dice[i] = random.randint(1,6)
        self.rolls_left -= 1

    def potential_scores(self):
        d = self.dice[:]
        counts = defaultdict(int)
        for x in d:
            counts[x] += 1
        total = sum(d)

        def upper(n):
            return sum(x for x in d if x == n)
        uniq = sorted(set(d))
        small_straight = 0
        for seq in ([1,2,3,4],[2,3,4,5],[3,4,5,6]):
            if all(s in uniq for s in seq):
                small_straight = 30
        large_straight = 40 if (uniq == [1,2,3,4,5] or uniq == [2,3,4,5,6]) else 0
        has_three = any(c >= 3 for c in counts.values())
        has_four  = any(c >= 4 for c in counts.values())
        five      = any(c == 5 for c in counts.values())
        pair      = any(c == 2 for c in counts.values())
        full_house = 25 if (has_three and pair) or five else 0

        return {
            'ones': upper(1), 'twos': upper(2), 'threes': upper(3),
            'fours': upper(4), 'fives': upper(5), 'sixes': upper(6),
            'three_kind': total if has_three else 0,
            'four_kind' : total if has_four  else 0,
            'full_house': full_house,
            'small_straight': small_straight,
            'large_straight': large_straight,
            'yahtzee': 50 if five else 0,
            'chance': total
        }

    def all_filled(self, p: Player) -> bool:
        return all(v is not None for v in p.score.values())

    def is_game_over(self) -> bool:
        return bool(self.players) and all(self.all_filled(pl) for pl in self.players)

    def standings(self):
        return [{
            'name': p.name,
            'upper': p.upper_sum(),
            'upperBonus': p.upper_bonus(),
            'lower': p.lower_sum(),
            'grand': p.total(),
        } for p in sorted(self.players, key=lambda x: x.total(), reverse=True)]

    def as_public_state(self):
        return {
            'players': [{
                'name': p.name,
                'score': p.score,
                'yahtzeeBonus': int(100 * p.bonus_yahtzees),
                'bonusYahtzees': int(p.bonus_yahtzees),
                'totals': {
                    'upper': p.upper_sum(),
                    'upperBonus': p.upper_bonus(),
                    'lower': p.lower_sum(),
                    'grand': p.total(),
                }
            } for p in self.players],
            'currentIndex': self.current_index,
            'dice': self.dice,
            'held': self.held,
            'rollsLeft': self.rolls_left,
            'started': self.started,
            'gameOver': self.is_game_over() and not self.started,
            'standings': self.standings() if self.is_game_over() else [],
            'categories': CATEGORIES,
        }

GAME = Game()

@app.route('/')
def index():
    return render_template_string(INDEX_HTML, categories=CATEGORIES)

@socketio.on('connect')
def on_connect():
    join_room(GAME.room)
    emit('state', GAME.as_public_state(), to=request.sid)

@socketio.on('join')
def on_join(data):
    data = data or {}
    device_id = str(data.get('deviceId', '')).strip()
    if not device_id:
        # Fallback: very rough fingerprint if the client didn't send one
        device_id = f"{request.remote_addr}|{request.headers.get('User-Agent','unknown')}"

    # Block if this device already has a player seated
    if any(p.device_id == device_id for p in GAME.players):
        emit('join_denied', 'This device is already in the game. Use your existing tab, or Exit first.')
        return

    # Also block if this connection SID already present
    if any(p.sid == request.sid for p in GAME.players):
        emit('join_denied', 'You are already joined.')
        return

    name = str(data.get('name','Player')).strip() or 'Player'
    existing = {p.name for p in GAME.players}
    base = name; i = 2
    while name in existing:
        name = f"{base} {i}"; i += 1

    GAME.players.append(Player(request.sid, name, device_id))
    if not GAME.started:
        GAME.current_index = 0
    broadcast_state()

@socketio.on('leave')
def on_leave():
    _remove_player_by_sid(request.sid)
    GAME.started = False
    GAME.reset_turn()
    if GAME.current_index >= len(GAME.players):
        GAME.current_index = 0
    broadcast_state()

@socketio.on('disconnect')
def on_disconnect():
    # Auto-clean on tab close / network drop
    _remove_player_by_sid(request.sid)
    if GAME.current_index >= len(GAME.players):
        GAME.current_index = 0
    broadcast_state()


def _remove_player_by_sid(sid: str) -> None:
    idx = next((i for i,p in enumerate(GAME.players) if p.sid == sid), None)
    if idx is not None:
        if idx <= GAME.current_index and GAME.players:
            GAME.current_index = max(0, GAME.current_index - 1)
        GAME.players.pop(idx)

@socketio.on('start_game')
def on_start():
    if not GAME.players:
        return
    GAME.started = True
    GAME.current_index = 0
    GAME.reset_turn()
    broadcast_state()

@socketio.on('roll')
def on_roll():
    if not is_current_player(request.sid):
        return
    if GAME.rolls_left <= 0:
        return
    GAME.roll()

    # Yahtzee locks further rolls; +100 if already have Yahtzee scored.
    p = GAME.current_player()
    if p and len(set(GAME.dice)) == 1:
        # removed auto-bonus; manual via set_bonus_yahtzees
        GAME.rolls_left = 0
        GAME.held = [True]*5
    broadcast_state()

@socketio.on('toggle_hold')
def on_toggle_hold(i):
    if not is_current_player(request.sid):
        return
    try:
        idx = int(i)
        if 0 <= idx < 5 and GAME.rolls_left < 3:
            GAME.held[idx] = not GAME.held[idx]
            broadcast_state()
    except Exception:
        pass

@socketio.on('score_category')
def on_score(cat):
    if not is_current_player(request.sid):
        return
    p = GAME.current_player()
    if p is None or cat not in CATEGORIES or p.score[cat] is not None:
        return
    if GAME.rolls_left == 3:  # must roll at least once
        return
    p.score[cat] = GAME.potential_scores()[cat]
    GAME.next_player_index()
    GAME.reset_turn()
    if GAME.is_game_over():
        GAME.started = False
    broadcast_state()

@socketio.on('set_bonus_yahtzees')
def on_set_bonus_yahtzees(data):
    if not is_current_player(request.sid):
        return
    p = GAME.current_player()
    if p is None:
        return
    try:
        count = int((data or {}).get('count', 0))
    except Exception:
        return
    # clamp between 0 and 3
    count = max(0, min(3, count))
    p.bonus_yahtzees = count
    broadcast_state()

@socketio.on('reset_game')
def on_reset():
    for p in GAME.players:
        p.score = {c: None for c in CATEGORIES}
        p.bonus_yahtzees = 0
    GAME.started = False
    GAME.current_index = 0
    GAME.reset_turn()
    broadcast_state()

@socketio.on('play_again')
def on_play_again():
    for p in GAME.players:
        p.score = {c: None for c in CATEGORIES}
        p.bonus_yahtzees = 0
    if not GAME.players:
        GAME.started = False
        GAME.current_index = 0
        GAME.reset_turn()
    else:
        GAME.started = True
        GAME.current_index = 0
        GAME.reset_turn()
    broadcast_state()

def is_current_player(sid: str) -> bool:
    cp = GAME.current_player()
    return cp is not None and cp.sid == sid and GAME.started


def broadcast_state():
    socketio.emit('state', GAME.as_public_state(), room=GAME.room)

INDEX_HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="color-scheme" content="light dark" />
  <title>🎲 Yahtzee</title>
  <script src="https://cdn.socket.io/4.7.5/socket.io.min.js" crossorigin="anonymous"></script>
  <style>
    /* ---------- Theme tokens ---------- */
    :root{
      --bg:#0b0f1a; --fg:#e5e7eb; --muted:#9ca3af; --card:#0f1628;
      --accent:#60a5fa; --accent-2:#34d399; --danger:#f87171;
      --shadow:0 10px 25px rgba(0,0,0,.35); --sep: rgba(148,163,184,.55);
      --dieA:#111827; --dieB:#0b1220; --dieBorder:rgba(255,255,255,.06);
      --dieInset:rgba(255,255,255,.05); --dieDrop:rgba(0,0,0,.45); --pip:#e5e7eb;
      --pad:10px; --radius:14px; --font:14px;
      color-scheme: dark light; /* supports both */
      /* Bonus track */
      .bonus-track{display:inline-flex;gap:6px;vertical-align:middle;margin-left:8px}
      .bonus-box{width:16px;height:16px;border:1px solid var(--sep);border-radius:4px;display:inline-block;cursor:pointer}
      .bonus-box.filled{background:var(--accent)}

    }
    @media (prefers-color-scheme: light){
      :root{
        --bg:#f6f7fb; --fg:#0f172a; --muted:#475569; --card:#ffffff;
        --accent:#3b82f6; --accent-2:#16a34a; --danger:#ef4444;
        --shadow:0 10px 25px rgba(0,0,0,.08); --sep: rgba(148,163,184,.45);
        --dieA:#ffffff; --dieB:#e9eef6; --dieBorder:rgba(0,0,0,.10);
        --dieInset:rgba(0,0,0,.15); --dieDrop:rgba(0,0,0,.20); --pip:#111;
      }
    }
    :root[data-theme="light"]{ color-scheme: light; }
    :root[data-theme="dark"]{ color-scheme: dark; }

    *{box-sizing:border-box}
    html,body{height:100%}
    body{
      margin:0;background:var(--bg);color:var(--fg);
      font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
      font-size:var(--font);
    }

    /* ---------- Layout ---------- */
    .shell{
      height:100dvh; display:grid; grid-template-rows:auto 1fr; gap:8px;
      padding:8px;
      padding-bottom:calc(8px + env(safe-area-inset-bottom,0px));
      padding-top:calc(8px + env(safe-area-inset-top,0px));
    }
    @supports not (height:100dvh){ .shell{height:100vh;} }

    header{display:flex;align-items:center;gap:8px}
    header .spacer{flex:1}
    .title{font-weight:800;letter-spacing:.3px}

    .grid{
      display:grid; gap:8px; height:100%;
      grid-template-columns: clamp(240px, 28vw, 340px) 1fr;
      grid-template-rows: 1fr;
      min-height:0;
    }
    .left{display:grid; grid-template-rows: 170px 1fr; gap:8px; min-height:0;}
    .right{min-height:0; display:grid; grid-template-rows: 1fr; }

    .card{background:var(--card); border:1px solid rgba(148,163,184,.25); border-radius:var(--radius); box-shadow:var(--shadow); padding:var(--pad); min-height:0;}
    .card h2{margin:0 0 6px; font-size:13px; opacity:.9}
    .hint{color:var(--muted); font-size:12px}

    .input{width:100%; padding:8px 10px; border-radius:10px; border:1px solid rgba(148,163,184,.35); background:transparent; color:var(--fg)}
    .btn{cursor:pointer; border:none; border-radius:10px; padding:8px 12px; font-weight:600}
    .btn.primary{background:var(--accent);color:#fff}
    .btn.success{background:var(--accent-2);color:#fff}
    .btn.ghost{background:transparent;border:1px solid rgba(148,163,184,.35);color:var(--fg)}
    .btn.danger{background:var(--danger);color:#fff}
    .btn:disabled{opacity:.5;cursor:not-allowed}

    .flex{display:flex; align-items:center; gap:8px; flex-wrap:wrap}
    .badge{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:999px;background:rgba(59,130,246,.10);color:var(--accent);font-size:12px;font-weight:700; white-space:nowrap}
    .pill{font-size:12px; padding:3px 6px; border-radius:999px; background:rgba(148,163,184,.18)}

    /* Dice */
    .dice-area{display:flex; align-items:center; gap:8px; flex-wrap:wrap; padding-bottom:2px;}
    .dice{display:flex; gap:8px; flex-wrap:wrap;}
    .die{
      width:clamp(42px, 6vh, 56px); height:clamp(42px, 6vh, 56px);
      background:linear-gradient(145deg,var(--dieA),var(--dieB));
      border-radius:12px; border:1px solid var(--dieBorder);
      box-shadow:0 5px 12px var(--dieInset) inset,0 6px 16px var(--dieDrop);
      position:relative; cursor:pointer; display:grid; place-items:center;
      transition: box-shadow .15s ease, border-color .15s ease, transform .05s ease;
    }
    .die:active{ transform: translateY(1px); }
    .pip{width:10px;height:10px;border-radius:50%;background:var(--pip);box-shadow:0 1px 0 rgba(0,0,0,.25) inset}
    .die.held{ border-color: var(--accent); box-shadow:0 0 0 3px var(--accent), 0 5px 12px var(--dieInset) inset, 0 6px 16px var(--dieDrop); }

    /* Players */
    .players{display:grid; gap:6px; overflow:auto; height:100%}
    .player{display:flex; align-items:center; justify-content:space-between; padding:6px 8px; border-radius:10px; border:1px dashed rgba(148,163,184,.35)}
    .player b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:160px;}

    /* Scorecard (right) */
    .score-wrap{height:100%; display:flex; flex-direction:column; min-height:0}
    .score-head{display:flex; align-items:center; gap:8px; margin-bottom:4px}
    .left, .right, .score-wrap, .score-body { min-width: 0; }
    .right { overflow: hidden; }
    .score-body{min-height:0; overflow:auto; border:1px solid rgba(148,163,184,.25); border-radius:12px; max-height:100%; padding-bottom:env(safe-area-inset-bottom,0px);}

    .score{table-layout:fixed; width:100%; border-collapse:collapse}
    .score th,.score td{padding:6px 8px; border-bottom:1px solid rgba(148,163,184,.25); text-align:left}
    .score thead th{background:rgba(148,163,184,.12); font-size:12px; position:sticky; top:0}
    .score tbody tr:hover td{background:rgba(148,163,184,.06)}
    .score th:nth-child(1){width:44%}
    .score th:nth-child(2), .score th:nth-child(3){width:28%}
    .score .clickable{cursor:pointer}
    .score .sep-row td{border-bottom:3px double var(--sep); position:relative}
    .score .sep-row td span{font-size:11px;color:var(--muted); position:absolute; left:8px; bottom:-10px; background:var(--card); padding:0 6px}
    .score .sum-row td{background:rgba(148,163,184,.08)}
    .score .sum-row.strong td{font-weight:700}
    .score .sum-row.grand td{font-size:1.02rem}

    @media (max-width: 760px){
      :root{ --pad:8px; --radius:12px; --font:13px; }
      .grid{ grid-template-columns: 180px 1fr; }
      .left{ grid-template-rows: 140px 1fr; }
      .die{ width:clamp(34px, 5.5vh, 46px); height:clamp(34px, 5.5vh, 46px); }
      .score th:nth-child(3), .score td:nth-child(3){ display:none; }
      #turnBadge{ font-size:10px; padding:2px 6px; line-height:1; }
      .btn{ padding:6px 10px; }
    }
    @media (max-width: 380px){
      .grid{ grid-template-columns: 160px 1fr; }
      .die{ width:32px; height:32px; }
      .btn{ padding:5px 9px; }
    }

    .modal{position:fixed; inset:0; background:rgba(0,0,0,.45); display:none; align-items:center; justify-content:center; padding:16px; padding-bottom:calc(16px + env(safe-area-inset-bottom,0px)); z-index:1000;}
    .modal.show{display:flex}
    .modal .dialog{background:var(--card); color:var(--fg); border-radius:14px; box-shadow:var(--shadow); padding:18px; max-width:520px; width:min(92vw,520px); max-height:calc(100dvh - 48px - env(safe-area-inset-bottom,0px)); overflow:auto;}
    .modal .dialog h3{margin:0 0 8px}
    .standings{display:grid; gap:6px; margin:8px 0}
    .standings .row{display:flex; justify-content:space-between; border:1px solid rgba(148,163,184,.25); border-radius:10px; padding:6px 10px}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="title">🎲 Yahtzee</div>
      <div class="spacer"></div>
      <button id="themeBtn" class="btn ghost" title="Toggle theme">🌓</button>
      <button id="leaveBtn" class="btn ghost">Exit</button>
      <button id="resetBtn" class="btn danger">Reset</button>
    </header>

    <div class="grid">
      <div class="left">
        <aside class="card">
          <h2>Join</h2>
          <div class="flex">
            <input id="name" class="input" placeholder="Your name" maxlength="18" />
            <button id="joinBtn" class="btn primary">Join</button>
          </div>
          <div class="hint" style="margin-top:6px;">Share this URL so friends on Wi‑Fi can join.</div>
          <div id="joinHint" class="hint" style="margin-top:6px;color:#f87171;display:none"></div>
        </aside>

        <section id="tableCard" class="card" style="display:grid; grid-template-rows: auto minmax(96px,auto) 1fr; gap:8px; min-height:0;">
          <div class="flex">
            <h2 style="margin:0;">Table</h2>
            <span id="turnBadge" class="badge" style="display:none;">Your turn</span>
            <div class="spacer"></div>
            <button id="startBtn" class="btn success">Start</button>
            <button id="rollBtn" class="btn primary">Roll (<span id="rollsLeft">3</span>)</button>
          </div>

          <div class="dice-area">
            <div id="dice" class="dice"></div>
            <div class="hint">Tap dice to hold after first roll</div>
          </div>

          <div class="players">
            <div class="flex" style="justify-content:space-between;">
              <h2 style="margin:0;">Players</h2>
              <div class="hint">👑 current player</div>
            </div>
            <div id="players" style="min-height:0;"></div>
          </div>
        </section>
      </div>

      <div class="right">
        <div class="card score-wrap">
          <div class="score-head">
            <h2 style="margin:0;">Scorecard</h2>
            <div class="hint">Roll at least once to score. Extra Yahtzees after the first are +100; any Yahtzee locks further rolls this turn.</div>
          </div>
          <div id="scoreContainer" class="score-body"></div>
        </div>
      </div>
    </div>
  </div>

  <div id="gameOverModal" class="modal" aria-hidden="true">
    <div class="dialog">
      <h3>Game over!</h3>
      <div class="hint">Final standings</div>
      <div id="standings" class="standings"></div>
      <div class="flex" style="justify-content:flex-end; margin-top:10px;">
        <button id="exitAfterBtn" class="btn ghost">Exit</button>
        <button id="playAgainBtn" class="btn primary">Play Again</button>
      </div>
    </div>
  </div>

<script>
  const socket = io();
  let state = null;

  // Theme toggle
  const themeBtn = document.getElementById('themeBtn');
  const THEME_KEY = 'yz_theme';
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  function applyTheme(mode){
    const root = document.documentElement;
    if (mode === 'dark'){ root.setAttribute('data-theme','dark'); }
    else if (mode === 'light'){ root.setAttribute('data-theme','light'); }
    else { root.removeAttribute('data-theme'); }
    themeBtn.textContent = mode === 'dark' ? '🌙' : mode === 'light' ? '☀️' : '🌓';
  }
  function nextTheme(cur){ return cur === 'system' ? 'dark' : cur === 'dark' ? 'light' : 'system'; }
  let themeMode = localStorage.getItem(THEME_KEY) || 'system';
  applyTheme(themeMode);
  themeBtn.onclick = () => { themeMode = nextTheme(themeMode); localStorage.setItem(THEME_KEY, themeMode); applyTheme(themeMode); };
  mq.addEventListener?.('change', () => { if ((localStorage.getItem(THEME_KEY) || 'system') === 'system'){ applyTheme('system'); } });

  // --- Single-join-per-device ---
  const DEVICE_KEY = 'yz_device';
  let deviceId = localStorage.getItem(DEVICE_KEY);
  if (!deviceId) {
    // crypto.randomUUID is supported in modern browsers
    deviceId = (crypto && crypto.randomUUID) ? crypto.randomUUID() : (Date.now()+''+Math.random());
    localStorage.setItem(DEVICE_KEY, deviceId);
  }

  // App wiring
  let myName = localStorage.getItem('yz_name') || '';
  const nameInput = document.getElementById('name');
  const joinBtn = document.getElementById('joinBtn');
  const startBtn = document.getElementById('startBtn');
  const rollBtn = document.getElementById('rollBtn');
  const resetBtn = document.getElementById('resetBtn');
  const leaveBtn = document.getElementById('leaveBtn');
  const diceEl = document.getElementById('dice');
  const playersEl = document.getElementById('players');
  const scoreContainer = document.getElementById('scoreContainer');
  const rollsLeftEl = document.getElementById('rollsLeft');
  const turnBadge = document.getElementById('turnBadge');
  const joinHint = document.getElementById('joinHint');

  const gameOverModal = document.getElementById('gameOverModal');
  const standingsEl = document.getElementById('standings');
  const playAgainBtn = document.getElementById('playAgainBtn');
  const exitAfterBtn = document.getElementById('exitAfterBtn');

  nameInput.value = myName;

  joinBtn.onclick = () => {
    const nm = nameInput.value.trim() || 'Player';
    myName = nm; localStorage.setItem('yz_name', myName);
    joinHint.style.display = 'none';
    socket.emit('join', { name: nm, deviceId });
  };
  startBtn.onclick = () => socket.emit('start_game');
  rollBtn.onclick = () => socket.emit('roll');
  resetBtn.onclick = () => socket.emit('reset_game');
  leaveBtn.onclick = () => { socket.emit('leave'); localStorage.removeItem('yz_name'); myName=''; };

  playAgainBtn.onclick = () => socket.emit('play_again');
  exitAfterBtn.onclick = () => { socket.emit('leave'); localStorage.removeItem('yz_name'); myName=''; };

  socket.on('state', (s) => { state = s; render(); });
  socket.on('join_denied', (msg) => {
    joinHint.textContent = msg || 'Already joined on this device.';
    joinHint.style.display = 'block';
  });

  function isMyTurn(){
    if (!state) return false;
    const meIdx = state.players.findIndex(p => p.name === myName);
    return state.started && meIdx === state.currentIndex;
  }
  function hasRolledThisTurn(){ return state && state.rollsLeft < 3; }

  function render(){
    startBtn.disabled = !state || state.started || state.players.length === 0;
    rollBtn.disabled = !isMyTurn() || state.rollsLeft <= 0;
    rollsLeftEl.textContent = state ? state.rollsLeft : '3';
    turnBadge.style.display = isMyTurn() ? 'inline-flex' : 'none';

    // Dice
    diceEl.innerHTML = '';
    (state?.dice || []).forEach((val, i) => {
      const held = state.held[i];
      const d = document.createElement('div');
      d.className = 'die' + (held ? ' held' : '');
      d.title = held ? 'Held' : 'Click to hold (after 1st roll)';
      d.onclick = () => { if (isMyTurn() && hasRolledThisTurn()) socket.emit('toggle_hold', i); };
      d.appendChild(renderPips(val));
      diceEl.appendChild(d);
    });

    // Players
    playersEl.innerHTML = '';
    (state?.players || []).forEach((p, idx) => {
      const row = document.createElement('div'); row.className = 'player';
      const left = document.createElement('div'); left.className = 'flex';
      if (idx === state.currentIndex && state.started){ const crown = document.createElement('span'); crown.textContent = '👑'; left.appendChild(crown); }
      const nm = document.createElement('b'); nm.textContent = p.name; left.appendChild(nm);
      const ttl = document.createElement('span'); ttl.className = 'pill'; ttl.textContent = `Total: ${p.totals?.grand ?? 0}`;
      row.appendChild(left); row.appendChild(ttl);
      playersEl.appendChild(row);
    });

    renderScorecard();
    maybeShowGameOver();
  }

  function renderScorecard(){
    if (!state) return;
    const meIdx = state.players.findIndex(p => p.name === myName);
    const myCard = meIdx >= 0 ? state.players[meIdx].score : null;
    const myBonusCount = meIdx >= 0 ? (state.players[meIdx].bonusYahtzees || 0) : 0;
    const myBonusPts = myBonusCount * 100;
    const t = meIdx >= 0 ? (state.players[meIdx].totals || {upper:0,upperBonus:0,lower:0,grand:0}) : {upper:0,upperBonus:0,lower:0,grand:0};
    const potential = (isMyTurn() && hasRolledThisTurn()) ? computePotential(state.dice) : {};

    const table = document.createElement('table');
    table.className = 'score';

    const upperRows = [
      ['Ones','ones'], ['Twos','twos'], ['Threes','threes'], ['Fours','fours'], ['Fives','fives'], ['Sixes','sixes']
    ].map(([label,key]) => rowHtml(label, key, myCard, potential)).join('');

    const sep = `<tr class="sep-row"><td colspan="3"><span>Lower Section</span></td></tr>`;

    const lowerRows = [
      ['Three of a Kind','three_kind'], ['Four of a Kind','four_kind'], ['Full House','full_house'],
      ['Small Straight','small_straight'], ['Large Straight','large_straight'], ['Yahtzee','yahtzee'], ['Chance','chance']
    ].map(([label,key]) => rowHtml(label, key, myCard, potential)).join('');

    const upperTotals = `
      <tr class="sum-row"><td><b>Upper Subtotal</b></td><td>${t.upper}</td><td></td></tr>
      <tr class="sum-row"><td><b>Upper Bonus</b></td><td>${t.upperBonus}</td><td class="hint">+35 if ≥ 63</td></tr>
      <tr class="sum-row strong"><td><b>Upper Total</b></td><td>${t.upper + t.upperBonus}</td><td></td></tr>`;

    const maxBonus = 3;
    const boxes = Array.from({length:maxBonus}, (_,i)=>`<span class="bonus-box ${i < myBonusCount ? 'filled' : ''}" data-idx="${i}"></span>`).join('');
    const bonusRow = `<tr><td>Yahtzee Bonus (+100 each)<div class="bonus-track">${boxes}</div></td><td>${myBonusPts>0?('+'+myBonusPts):'—'}</td><td class="hint"></td></tr>`;

    const lowerTotals = `
      <tr class="sum-row strong"><td><b>Lower Total</b></td><td>${t.lower}</td><td></td></tr>
      <tr class="sum-row grand"><td><b>Grand Total</b></td><td>${t.grand}</td><td></td></tr>`;

    table.innerHTML = `
      <thead>
        <tr><th>Category</th><th>Your Score</th><th class="hint">Potential</th></tr>
      </thead>
      <tbody>
        ${upperRows}
        ${upperTotals}
        ${sep}
        ${lowerRows}
        ${bonusRow}
        ${lowerTotals}
      </tbody>`;

    scoreContainer.innerHTML = '';
    scoreContainer.appendChild(table);
    table.addEventListener('click', (e)=>{
      const el = e.target.closest('.bonus-box');
      if(!el) return;
      if (!isMyTurn()) return;
      const idx = parseInt(el.getAttribute('data-idx'),10);
      let newCount = idx + 1;
      if (idx < (myBonusCount)) {
        if (idx === myBonusCount - 1) newCount = idx; 
      }
      socket.emit('set_bonus_yahtzees', { count: newCount });
    });

  }

  function rowHtml(label, key, myCard, potential){
    const val = myCard ? myCard[key] : null;
    const pot = potential[key];
    const clickable = isMyTurn() && hasRolledThisTurn() && (val === null || typeof val === 'undefined') ? 'clickable' : '';
    const cell = `<td class="${clickable}" ${clickable?`onclick="onPick('${key}')"`:''}>${(val===null||typeof val==='undefined')?'—':val}</td>`;
    return `<tr><td>${label}</td>${cell}<td class="hint">${(pot!==undefined&&pot!==null)?pot:''}</td></tr>`;
  }

  window.onPick = (key) => {
    if (!isMyTurn() || !hasRolledThisTurn()) return;
    socket.emit('score_category', key);
  }

  function renderPips(n){
    const grid = document.createElement('div');
    grid.style.display='grid'; grid.style.gridTemplateColumns='repeat(3, 1fr)'; grid.style.gap='5px';
    const map = { 1:[5], 2:[1,9], 3:[1,5,9], 4:[1,3,7,9], 5:[1,3,5,7,9], 6:[1,3,4,6,7,9] };
    for (let i=1;i<=9;i++){
      const cell = document.createElement('div');
      cell.style.width='12px'; cell.style.height='12px'; cell.style.display='grid'; cell.style.placeItems='center';
      if (map[n].includes(i)){ const pip = document.createElement('div'); pip.className='pip'; cell.appendChild(pip); }
      grid.appendChild(cell);
    }
    return grid;
  }

  function computePotential(d){
    const counts = Array(7).fill(0); d.forEach(x=>counts[x]++);
    const total = d.reduce((a,b)=>a+b,0);
    const uniq = [...new Set(d)].sort((a,b)=>a-b);
    const upper = n => d.filter(x=>x===n).reduce((a,b)=>a+b,0);

    let small = 0; [[1,2,3,4],[2,3,4,5],[3,4,5,6]].forEach(seq=>{ if (seq.every(s=>uniq.includes(s))) small = 30; });
    const large = (uniq.toString()==='1,2,3,4,5'||uniq.toString()==='2,3,4,5,6') ? 40 : 0;
    const has3 = counts.some(c=>c>=3);
    const has4 = counts.some(c=>c>=4);
    const five = counts.some(c=>c===5);
    const pair = counts.some(c=>c===2);
    const full = (has3 && pair) || five ? 25 : 0;

    return { ones:upper(1), twos:upper(2), threes:upper(3), fours:upper(4), fives:upper(5), sixes:upper(6),
             three_kind:has3?total:0, four_kind:has4?total:0, full_house:full, small_straight:small, large_straight:large,
             yahtzee:five?50:0, chance:total };
  }

  function maybeShowGameOver(){
    if (!state) return;
    const show = !!state.gameOver;
    const modal = document.getElementById('gameOverModal');
    modal.classList.toggle('show', show);
    modal.setAttribute('aria-hidden', String(!show));
    if (show){
      standingsEl.innerHTML = '';
      (state.standings || []).forEach((row, i) => {
        const div = document.createElement('div'); div.className = 'row';
        div.innerHTML = `<div>#${i+1} — <b>${row.name}</b></div><div>${row.grand}</div>`;
        standingsEl.appendChild(div);
      });
    }
  }
</script>
</body>
</html>
"""

if __name__ == '__main__':
    print("\nYahtzee server starting...")
    print("Open on this PC: http://localhost:5000")
    print("Open on other devices: http://<192.168.2.31>:5000  (e.g., 192.168.x.x)")
    socketio.run(app, host='0.0.0.0', port=PORT)
