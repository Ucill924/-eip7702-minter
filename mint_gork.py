"""
mint_gork.py — Mint $GORK fully automated
Flow:
  1. Auto SIWE login → dapat bind_token + mcp_url
  2. MCP session initialize
  3. Mint loop via MCP relay

Pakai wallets.json — tidak perlu login manual!

Usage:
    python mint_gork.py              # loop semua wallet
    python mint_gork.py --slots 3    # 3 slot per TX
    python mint_gork.py --once       # mint sekali saja
    python mint_gork.py --all        # semua wallet (tidak filter delegated)
    python mint_gork.py --status     # cek status saja

Requirements:
    pip install web3 eth-account requests
"""

import argparse
import json
import os
import re
import sys
import time
import threading
from datetime import datetime, timezone

import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

# ── CONFIG ────────────────────────────────────────────────────────────────────
WALLETS_FILE  = "wallets.json"
GORK_BASE     = "https://gorkshit.meme"
PREAUTH_URL   = f"{GORK_BASE}/siwe/preauth"
NONCE_URL     = f"{GORK_BASE}/siwe/nonce"
MCP_BASE      = f"{GORK_BASE}/mcp"

LOOP_DELAY    = 60
RETRY_DELAY   = 15
TOKEN_REFRESH = 3600 * 20  # refresh token setiap 20 jam (expires 24 jam)
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "Content-Type" : "application/json",
    "Accept"       : "application/json, text/event-stream",
    "Referer"      : "https://gorkshit.meme/",
    "Origin"       : "https://gorkshit.meme",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
}


def load_wallets(all_wallets=False) -> list:
    if not os.path.exists(WALLETS_FILE):
        print(f"❌ {WALLETS_FILE} tidak ditemukan!")
        sys.exit(1)
    with open(WALLETS_FILE) as f:
        wallets = json.load(f)
    if all_wallets:
        return wallets
    active = [w for w in wallets if w.get("delegated")]
    if not active:
        print("⚠  Tidak ada wallet delegated — pakai --all")
        sys.exit(1)
    return active


def get_nonce() -> str:
    """Ambil nonce dari server untuk SIWE message."""
    try:
        resp = requests.get(NONCE_URL, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("nonce") or data.get("data") or resp.text.strip().strip('"')
    except:
        pass
    # Fallback: generate random nonce
    import secrets, string
    return ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(11))


def build_siwe_message(address: str, nonce: str) -> str:
    """Build SIWE message persis seperti yang dipakai browser."""
    issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
                f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
    return (
        f"gorkshit.meme wants you to sign in with your Ethereum account:\n"
        f"{address}\n\n"
        f"Sign in to gorkshit so grok can mint $GORK to this wallet.\n\n"
        f"URI: https://gorkshit.meme\n"
        f"Version: 1\n"
        f"Chain ID: 1\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at}"
    )


def siwe_login(address: str, private_key: str) -> dict | None:
    """
    Auto SIWE login:
    1. Get nonce
    2. Build + sign SIWE message
    3. POST ke /siwe/preauth
    Returns: {"bind_token": ..., "mcp_url": ..., "expires_in": ...}
    """
    try:
        # 1. Get nonce
        nonce = get_nonce()
        print(f"    Nonce: {nonce}")

        # 2. Build SIWE message
        message = build_siwe_message(address, nonce)

        # 3. Sign message
        msg_hash   = encode_defunct(text=message)
        signed     = Account.sign_message(msg_hash, private_key=private_key)
        signature  = signed.signature.hex()
        if not signature.startswith("0x"):
            signature = "0x" + signature

        # 4. POST preauth
        payload = {"message": message, "signature": signature}
        resp    = requests.post(PREAUTH_URL, json=payload, headers=HEADERS, timeout=15)

        if resp.status_code != 200:
            print(f"    ❌ Preauth failed: {resp.status_code} {resp.text[:200]}")
            return None

        data = resp.json()
        if not data.get("ok"):
            print(f"    ❌ Preauth error: {data}")
            return None

        print(f"    ✅ Login OK | delegated={data.get('is_7702_delegated')} | expires={data.get('expires_in')}s")
        return data

    except Exception as e:
        print(f"    ❌ SIWE login error: {e}")
        return None


def parse_sse(text: str) -> str:
    """Parse SSE response."""
    result = ""
    for line in text.splitlines():
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                data    = json.loads(data_str)
                content = (data.get("result") or {}).get("content", [])
                result += " ".join(c.get("text", "") for c in content if c.get("type") == "text")
                if not content and "error" in data:
                    result = f"ERROR: {data['error'].get('message', data['error'])}"
            except:
                pass
    return result or text.strip()


class GorkSession:
    def __init__(self, address: str, private_key: str):
        self.address     = address
        self.private_key = private_key
        self.mcp_url     = None
        self.session_id  = None
        self.login_time  = 0
        self.tag         = address[:6] + "..." + address[-4:]

    def login(self) -> bool:
        """SIWE login dan dapat mcp_url."""
        print(f"  [{self.tag}] 🔑 SIWE login...")
        data = siwe_login(self.address, self.private_key)
        if not data:
            return False
        self.mcp_url    = data["mcp_url"]
        self.login_time = time.time()
        self.session_id = None  # reset session
        return True

    def initialize(self) -> bool:
        """Initialize MCP session."""
        if not self.mcp_url:
            if not self.login():
                return False

        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method" : "initialize",
            "params" : {
                "protocolVersion": "2024-11-05",
                "capabilities"   : {},
                "clientInfo"     : {"name": "gork-bot", "version": "1.0"},
            },
        }
        try:
            resp = requests.post(self.mcp_url, json=payload, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"  [{self.tag}] ❌ Init failed: {resp.status_code}")
                return False

            self.session_id = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
            if not self.session_id:
                print(f"  [{self.tag}] ❌ No session ID")
                return False

            # Send initialized notification
            notif   = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            headers = {**HEADERS, "mcp-session-id": self.session_id}
            requests.post(self.mcp_url, json=notif, headers=headers, timeout=10)

            print(f"  [{self.tag}] ✅ Session: {self.session_id[:8]}...")
            return True

        except Exception as e:
            print(f"  [{self.tag}] ❌ Init error: {e}")
            return False

    def call(self, tool: str, args: dict, retry=True) -> str:
        """Call MCP tool."""
        # Re-login kalau token hampir expired
        if self.login_time and time.time() - self.login_time > TOKEN_REFRESH:
            print(f"  [{self.tag}] 🔄 Token refresh...")
            self.login()

        if not self.session_id:
            if not self.initialize():
                return "ERROR: no session"

        headers = {**HEADERS, "mcp-session-id": self.session_id}
        payload = {
            "jsonrpc": "2.0", "id": 2,
            "method" : "tools/call",
            "params" : {"name": tool, "arguments": args},
        }
        try:
            resp = requests.post(self.mcp_url, json=payload, headers=headers, timeout=60)

            if resp.status_code in (400, 401) and retry:
                print(f"  [{self.tag}] ⚠ Session/token expired, re-login...")
                self.session_id = None
                if self.login() and self.initialize():
                    return self.call(tool, args, retry=False)
                return "ERROR: re-login failed"

            return parse_sse(resp.text)

        except Exception as e:
            return f"ERROR: {e}"

    def check_status(self) -> str:
        return self.call("check_gork_status", {})

    def mint(self, slots: int = 1) -> str:
        return self.call("mint_gork", {"count": slots})


def mint_loop(wallet: dict, slots: int, once: bool, stop_event: threading.Event):
    """Loop mint untuk satu wallet."""
    address     = wallet["address"]
    private_key = wallet["private_key"]
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    sess = GorkSession(address, private_key)
    loop = 0

    # Login + init session
    if not sess.login() or not sess.initialize():
        print(f"  [{sess.tag}] ❌ Gagal setup session — skip")
        return

    while not stop_event.is_set():
        loop += 1
        print(f"\n{'='*50}")
        print(f"  LOOP #{loop} — {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Wallet: {address}")
        print(f"{'='*50}")

        # Status
        try:
            print(">>> check_gork_status")
            status = sess.check_status()
            print(status)

            if "slots used: 10" in status or "slots remaining: 0" in status:
                print(f"  ✅ Max slots tercapai — stop")
                break

        except Exception as e:
            print(f"  ✗ Status error: {e}")
            time.sleep(RETRY_DELAY)
            continue

        # Mint
        try:
            print(f"\n>>> mint_gork (count={slots})")
            result = sess.mint(slots)
            print(result)

            if "ERROR" in result:
                time.sleep(RETRY_DELAY)
                continue

        except Exception as e:
            print(f"  ✗ Mint error: {e}")
            time.sleep(RETRY_DELAY)
            continue

        if once:
            print(f"\n  ✓ Done (--once)")
            break

        print(f"\n  ✓ Loop #{loop} done. Waiting {LOOP_DELAY}s...\n")
        if not stop_event.is_set():
            time.sleep(LOOP_DELAY)


def ask_slots() -> int:
    """Tanya jumlah slot secara interaktif."""
    print("\n┌─────────────────────────────────────┐")
    print("│   Berapa slot yang mau di-mint?      │")
    print("│   (1 slot = 10M $GORK + 0.00111 ETH) │")
    print("│   (min: 1, max: 10)                  │")
    print("└─────────────────────────────────────┘")
    while True:
        try:
            val = input("  Jumlah slot → ").strip()
            slots = int(val)
            if 1 <= slots <= 10:
                return slots
            print("  ❌ Harus antara 1-10, input lagi...")
        except ValueError:
            print("  ❌ Input angka saja...")


def main():
    parser = argparse.ArgumentParser(description="Mint $GORK — fully automated")
    parser.add_argument("--slots",  type=int, default=None,    help="Slot per TX (1-10). Kalau tidak diisi, akan ditanya interaktif.")
    parser.add_argument("--once",   action="store_true",        help="Mint sekali saja")
    parser.add_argument("--all",    action="store_true",        help="Semua wallet")
    parser.add_argument("--status", action="store_true",        help="Cek status saja")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  Mint $GORK — gorkshit.meme (Auto SIWE)")
    print(f"{'='*55}")

    wallets = load_wallets(all_wallets=args.all)
    print(f"  Wallets : {len(wallets)}")
    for w in wallets:
        print(f"  • {w['address']}")

    # Tanya slots interaktif kalau tidak diisi
    if args.slots is None and not args.status:
        slots = ask_slots()
    else:
        slots = args.slots or 1

    slots = min(slots, 10)
    eth_total = 0.00111 * slots * len(wallets)
    print(f"\n  Slots/TX : {slots}")
    print(f"  ETH/TX   : {0.00111 * slots:.5f} ETH per wallet")
    print(f"  Est. total: ~{eth_total:.5f} ETH ({len(wallets)} wallet × {slots} slot)")

    # Konfirmasi + pilih mode
    if not args.status:
        print(f"\n  Mode mint:")
        print(f"  [1] Sekali saja ({slots} slot total)")
        print(f"  [2] Loop terus sampai {slots} slot × habis atau Ctrl+C")
        while True:
            mode = input("  Pilih mode (1/2) → ").strip()
            if mode in ("1", "2"):
                break
            print("  ❌ Input 1 atau 2")
        if mode == "1":
            args.once = True

        eth_total = 0.00111 * slots * len(wallets) * (1 if args.once else 10)
        print(f"\n  Mode     : {'Sekali saja' if args.once else 'Loop sampai max'}")
        confirm = input(f"  Lanjut? (y/n) → ").strip().lower()
        if confirm != "y":
            print("  Dibatalkan.")
            sys.exit(0)

    if args.status:
        for w in wallets:
            pk = w["private_key"]
            if not pk.startswith("0x"):
                pk = "0x" + pk
            sess = GorkSession(w["address"], pk)
            if sess.login() and sess.initialize():
                print(f"\n{w['address']}")
                print(sess.check_status())
        return

    print(f"\n🚀 Mulai mint... (Ctrl+C untuk stop)\n")

    stop_event = threading.Event()
    threads    = []

    for wallet in wallets:
        t = threading.Thread(
            target=mint_loop,
            args=(wallet, slots, args.once, stop_event),
            daemon=True,
        )
        t.start()
        threads.append(t)
        time.sleep(3)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n\n🛑 Stopping...")
        stop_event.set()
        for t in threads:
            t.join(timeout=10)

    print("\n✅ Selesai.\n")


if __name__ == "__main__":
    main()
