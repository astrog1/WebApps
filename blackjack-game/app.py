import os
import random
import string
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit

# -----------------------
# Config
# -----------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "ruywioaojbvytf")
HIT_SOFT_17 = True
BLACKJACK_PAYOUT = (3, 2)
NUM_DECKS = 6
MAX_PLAYERS = 6
MIN_BET = 5
MAX_BET = 500

# NEW: Visual pacing for dealer reveal/draws (seconds)
DEALER_REVEAL_DELAY = float(os.environ.get("DEALER_REVEAL_DELAY", 0.9))
DEALER_DRAW_DELAY = float(os.environ.get("DEALER_DRAW_DELAY", 0.9))

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

RANKS = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"]
SUITS = ["♠","♥","♦","♣"]

# -----------------------
# Helpers
# -----------------------

def new_shoe(n_decks=NUM_DECKS):
    cards = [(r, s) for r in RANKS for s in SUITS] * n_decks
    random.shuffle(cards)
    return cards


def hand_value(hand: List[Tuple[str, str]]):
    total = 0
    aces = 0
    for r, _ in hand:
        if r in ("10","J","Q","K"):
            total += 10
        elif r == "A":
            total += 11
            aces += 1
        else:
            total += int(r)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    soft = aces > 0 and total <= 21
    return total, soft


def is_blackjack(hand):
    return len(hand) == 2 and hand_value(hand)[0] == 21


def code(n=4):
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(n))


# -----------------------
# Data Models
# -----------------------
@dataclass
class Player:
    sid: str
    name: str
    chips: int = 1000
    hands: List[List[Tuple[str, str]]] = field(default_factory=list)
    bets: List[int] = field(default_factory=list)
    insured: bool = False
    surrendered: bool = False
    seated: bool = False
    last_action_ts: float = 0.0
    last_results: List[str] = field(default_factory=list)  # NEW

    def clear_round(self):
        self.hands = []
        self.bets = []
        self.insured = False
        self.surrendered = False
        # keep last_results until after payouts next round


@dataclass
class Room:
    code: str
    players: Dict[str, Player] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)
    dealer: List[Tuple[str, str]] = field(default_factory=list)
    shoe: List[Tuple[str, str]] = field(default_factory=list)
    discard: List[Tuple[str, str]] = field(default_factory=list)
    phase: str = "lobby"
    turn_i: int = 0
    hand_i: int = 0
    min_bet: int = MIN_BET
    max_bet: int = MAX_BET

    def reset_shoe_if_needed(self):
        if len(self.shoe) < 52:
            self.shoe.extend(self.discard)
            self.discard = []
            random.shuffle(self.shoe)

    def next_turn(self):
        self.hand_i = 0
        while True:
            self.turn_i += 1
            if self.turn_i >= len(self.order):
                return False
            sid = self.order[self.turn_i]
            p = self.players.get(sid)
            if p and p.seated and len(p.hands) > 0:
                return True

    def current_player(self) -> Optional['Player']:
        if 0 <= self.turn_i < len(self.order):
            sid = self.order[self.turn_i]
            return self.players.get(sid)
        return None


ROOMS: Dict[str, Room] = {}


# -----------------------
# Flask routes
# -----------------------
@app.get("/")
def index():
    return render_template("index.html", min_bet=MIN_BET, max_bet=MAX_BET)


# -----------------------
# Dealer + Payouts (WITH DELAYS)
# -----------------------

def dealer_play_and_payout(room: Room):
    """Original immediate-resolution function kept for reference (unused)."""
    room.phase = "dealer"
    while True:
        dv, soft = hand_value(room.dealer)
        if dv < 17 or (HIT_SOFT_17 and dv == 17 and soft):
            room.dealer.append(room.shoe.pop())
        else:
            break
    _payout_and_reset(room)


def dealer_play_and_payout_with_delays(room: Room):
    """Step the dealer's actions with small sleeps and interim state emits.

    Runs in a Socket.IO background task to avoid blocking other clients.
    """
    # Reveal the hole card first
    room.phase = "dealer"
    emit_room_state(room.code)
    socketio.sleep(DEALER_REVEAL_DELAY)

    # Draw step-by-step
    while True:
        dv, soft = hand_value(room.dealer)
        if dv < 17 or (HIT_SOFT_17 and dv == 17 and soft):
            room.dealer.append(room.shoe.pop())
            emit_room_state(room.code)  # show the newly drawn card
            socketio.sleep(DEALER_DRAW_DELAY)
        else:
            break

    _payout_and_reset(room)


def _payout_and_reset(room: Room):
    room.phase = "payouts"
    dealer_total, _ = hand_value(room.dealer)
    dealer_bj = is_blackjack(room.dealer)

    for sid in room.order:
        p = room.players.get(sid)
        if not p or not p.bets:
            continue
        # ensure results list matches number of hands
        n = max(1, len(p.hands))
        if len(p.last_results) != n:
            p.last_results = [""] * n
        for i, hand in enumerate(p.hands):
            bet = p.bets[i]
            if len(hand) >= 3 and hand[0][0] == "X":
                p.last_results[i] = f"Surrender -{bet//2}"
                continue
            pt, _ = hand_value(hand)
            player_bj = is_blackjack(hand)

            if player_bj and not dealer_bj:
                p.chips += bet + (bet * BLACKJACK_PAYOUT[0] // BLACKJACK_PAYOUT[1])
                p.last_results[i] = f"Blackjack +{bet * BLACKJACK_PAYOUT[0] // BLACKJACK_PAYOUT[1]}"
            elif dealer_bj and not player_bj:
                p.last_results[i] = f"Lose -{bet}"
            else:
                if pt > 21:
                    p.last_results[i] = f"Bust -{bet}"
                elif dealer_total > 21 or pt > dealer_total:
                    p.chips += bet * 2
                    p.last_results[i] = f"Win +{bet}"
                elif pt == dealer_total:
                    p.chips += bet
                    p.last_results[i] = "Push ±0"
                else:
                    p.last_results[i] = f"Lose -{bet}"

    # discard
    for sid in room.order:
        if sid in room.players:
            for h in room.players[sid].hands:
                room.discard.extend(h)
    room.discard.extend(room.dealer)

    # Move back to betting phase and keep last_results visible
    room.phase = "betting"
    room.turn_i = 0
    room.hand_i = 0

    for sid in room.order:
        if sid in room.players:
            room.players[sid].hands = []
            room.players[sid].insured = False
            room.players[sid].surrendered = False

    emit_room_state(room.code)


# -----------------------
# Socket.IO events (updated to use delayed dealer task)
# -----------------------
@socketio.on("create_room")
def on_create_room(data):
    nickname = (data or {}).get("name", "Player")[:20]
    rid = code()
    while rid in ROOMS:
        rid = code()
    room = Room(code=rid, shoe=new_shoe())
    ROOMS[rid] = room

    p = Player(sid=request.sid, name=nickname)
    room.players[request.sid] = p
    if request.sid not in room.order:
        room.order.append(request.sid)

    join_room(rid)
    emit_room_state(rid)


@socketio.on("join_room")
def on_join_room(data):
    rid = (data or {}).get("code", "").upper().strip()
    nickname = (data or {}).get("name", "Player")[:20]
    room = ROOMS.get(rid)
    if not room:
        socketio.emit("error", {"message": "Room not found."})
        return

    p = Player(sid=request.sid, name=nickname)
    room.players[request.sid] = p
    if request.sid not in room.order:
        room.order.append(request.sid)

    join_room(rid)
    emit_room_state(rid)


@socketio.on("leave_room")
def on_leave_room(data):
    rid = (data or {}).get("code", "").upper().strip()
    room = ROOMS.get(rid)
    if not room:
        return
    leave_room(rid)
    emit_room_state(rid)


@socketio.on("take_seat")
def on_take_seat(data):
    rid = (data or {}).get("code", "").upper().strip()
    room = ROOMS.get(rid)
    if not room:
        return
    p = room.players.get(request.sid)
    if not p:
        return
    seated_count = sum(1 for sid in room.order if room.players.get(sid) and room.players[sid].seated)
    if seated_count >= MAX_PLAYERS:
        socketio.emit("error", {"message": "Table is full."})
        return
    p.seated = True
    emit_room_state(rid)


@socketio.on("stand_up")
def on_stand_up(data):
    rid = (data or {}).get("code", "").upper().strip()
    room = ROOMS.get(rid)
    if not room:
        return
    p = room.players.get(request.sid)
    if not p:
        return
    p.seated = False
    emit_room_state(rid)


@socketio.on("place_bet")
def on_place_bet(data):
    rid = (data or {}).get("code", "").upper().strip()
    amount = int((data or {}).get("amount", 0))
    room = ROOMS.get(rid)
    if not room or room.phase not in ("lobby", "betting"):
        return
    p = room.players.get(request.sid)
    if not p or not p.seated:
        return
    amount = max(room.min_bet, min(room.max_bet, amount))
    if amount > p.chips:
        socketio.emit("error", {"message": "Not enough chips."})
        return
    room.phase = "betting"
    p.clear_round()
    p.bets = [amount]
    p.chips -= amount
    emit_room_state(rid)


@socketio.on("start_round")
def on_start_round(data):
    rid = (data or {}).get("code", "").upper().strip()
    room = ROOMS.get(rid)
    if not room:
        return
    if not any(room.players[sid].bets for sid in room.order if sid in room.players and room.players[sid].seated):
        socketio.emit("error", {"message": "At least one seated player must bet."})
        return

    room.phase = "dealing"
    room.dealer = []
    room.reset_shoe_if_needed()

    for sid in room.order:
        if sid in room.players:
            room.players[sid].hands = []
            room.players[sid].insured = False
            room.players[sid].surrendered = False

    for _ in range(2):
        for sid in room.order:
            p = room.players.get(sid)
            if not p or not p.seated or not p.bets:
                continue
            card = room.shoe.pop()
            if not p.hands:
                p.hands = [[card]]
            else:
                p.hands[0].append(card)
        room.dealer.append(room.shoe.pop())

    upcard = room.dealer[0]
    if upcard[0] == "A":
        room.phase = "insurance"
        room.turn_i = -1
        room.next_turn()
        emit_room_state(rid)
        return

    room.phase = "acting"
    room.turn_i = -1
    room.next_turn()
    emit_room_state(rid)


@socketio.on("buy_insurance")
def on_buy_insurance(data):
    rid = (data or {}).get("code", "").upper().strip()
    buy = bool((data or {}).get("buy", False))
    room = ROOMS.get(rid)
    if not room or room.phase != "insurance":
        return
    p = room.current_player()
    if not p or p.sid != request.sid or not p.bets:
        return
    if buy and not p.insured:
        ins_cost = p.bets[0] // 2
        if p.chips >= ins_cost:
            p.chips -= ins_cost
            p.insured = True
    if not room.next_turn():
        dealer_blackjack = is_blackjack(room.dealer)
        if dealer_blackjack:
            room.phase = "payouts"
            for sid in room.order:
                player = room.players.get(sid)
                if not player or not player.bets:
                    continue
                if player.insured:
                    ins_cost = player.bets[0] // 2
                    player.chips += ins_cost * 3
                if is_blackjack(player.hands[0]):
                    player.chips += player.bets[0]
            emit_room_state(rid)
            room.phase = "betting"
        else:
            room.phase = "acting"
            room.turn_i = -1
            room.next_turn()
            emit_room_state(rid)
    else:
        emit_room_state(rid)


@socketio.on("action")
def on_action(data):
    rid = (data or {}).get("code", "").upper().strip()
    act = (data or {}).get("act", "").lower()
    room = ROOMS.get(rid)
    if not room or room.phase != "acting":
        return
    p = room.current_player()
    if not p or p.sid != request.sid:
        return

    now = time.time()
    if now - p.last_action_ts < 0.2:
        return
    p.last_action_ts = now

    cur = p.hands[room.hand_i]

    def can_split():
        return len(cur) == 2 and cur[0][0] == cur[1][0] and p.chips >= p.bets[room.hand_i]

    def can_double():
        return len(cur) == 2 and p.chips >= p.bets[room.hand_i]

    def _maybe_start_dealer():
        # Launch the delayed dealer sequence in a background task
        socketio.start_background_task(dealer_play_and_payout_with_delays, room)

    if act == "hit":
        cur.append(room.shoe.pop())
        if hand_value(cur)[0] > 21:
            if room.hand_i + 1 < len(p.hands):
                room.hand_i += 1
            else:
                if not room.next_turn():
                    _maybe_start_dealer()
        emit_room_state(rid)
        return

    if act == "stand":
        if room.hand_i + 1 < len(p.hands):
            room.hand_i += 1
        else:
            if not room.next_turn():
                _maybe_start_dealer()
        emit_room_state(rid)
        return

    if act == "double" and can_double():
        p.chips -= p.bets[room.hand_i]
        p.bets[room.hand_i] *= 2
        cur.append(room.shoe.pop())
        if room.hand_i + 1 < len(p.hands):
            room.hand_i += 1
        else:
            if not room.next_turn():
                _maybe_start_dealer()
        emit_room_state(rid)
        return

    if act == "split" and can_split():
        left = [cur[0]]
        right = [cur[1]]
        p.hands[room.hand_i] = left
        p.hands.insert(room.hand_i + 1, right)
        cost = p.bets[room.hand_i]
        p.chips -= cost
        p.bets.insert(room.hand_i + 1, cost)
        p.hands[room.hand_i].append(room.shoe.pop())
        p.hands[room.hand_i + 1].append(room.shoe.pop())
        emit_room_state(rid)
        return

    if act == "surrender" and len(cur) == 2 and not p.surrendered:
        refund = p.bets[room.hand_i] // 2
        p.surrendered = True
        p.chips += refund
        p.hands[room.hand_i] = [("X","X"),("X","X"),("X","X")]
        if room.hand_i + 1 < len(p.hands):
            room.hand_i += 1
        else:
            if not room.next_turn():
                _maybe_start_dealer()
        emit_room_state(rid)
        return

    socketio.emit("error", {"message": "Invalid action or insufficient chips."})


@socketio.on("disconnect")
def on_disconnect():
    pass


# -----------------------
# State broadcast (INCLUDES hand_values, dealer_total, last_results)
# -----------------------

def public_state(room: Room, viewer_sid: Optional[str] = None):
    reveal_dealer = room.phase in ("acting", "dealer", "payouts")

    players = []
    for sid in room.order:
        p = room.players.get(sid)
        if not p:
            continue
        hand_values = []
        for h in (p.hands or []):
            t, soft = hand_value(h)
            hand_values.append({"total": t, "soft": soft})
        entry = {
            "sid": sid,
            "name": p.name,
            "chips": p.chips,
            "seated": p.seated,
            "bets": p.bets,
            "hands": [[f"{r}{s}" for r, s in h] for h in (p.hands or [])],
            "hand_values": hand_values,            # NEW
            "last_results": p.last_results,        # NEW
            "me": (sid == viewer_sid),
        }
        players.append(entry)

    state = {
        "code": room.code,
        "phase": room.phase,
        "min_bet": room.min_bet,
        "max_bet": room.max_bet,
        "dealer": [f"{r}{s}" for r, s in (room.dealer if reveal_dealer else room.dealer[:1])],
        "dealer_total": hand_value(room.dealer)[0] if reveal_dealer and room.dealer else None,  # NEW
        "turn_sid": room.order[room.turn_i] if 0 <= room.turn_i < len(room.order) else None,
        "hand_i": room.hand_i,
        "players": players,
        "max_players": MAX_PLAYERS,
    }
    return state


def emit_room_state(rid: str):
    room = ROOMS.get(rid)
    if not room:
        return
    for sid in room.players.keys():
        socketio.emit("state", public_state(room, viewer_sid=sid), room=sid)
    socketio.emit("state", public_state(room), room=rid)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    socketio.run(app, host="0.0.0.0", port=port)
