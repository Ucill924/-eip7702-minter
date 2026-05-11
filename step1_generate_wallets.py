import argparse
import json
import os
import sys
import time

from eth_account import Account
from mnemonic import Mnemonic
from web3 import Web3

Account.enable_unaudited_hdwallet_features()

CONFIG_FILE  = "main_wallet_config.json"
WALLETS_FILE = "wallets.json"


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ File {CONFIG_FILE} tidak ditemukan!")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    if "YOUR_MAIN" in cfg["private_key"] or "YOUR_API" in cfg["rpc_url"]:
        print("❌ Edit main_wallet_config.json dulu — isi private_key dan rpc_url!")
        sys.exit(1)
    return cfg


def ask_wallet_count() -> int:
    """Tanya jumlah wallet secara interaktif."""
    print("\n┌─────────────────────────────────────┐")
    print("│   Berapa wallet minter yang dibuat?  │")
    print("│   (min: 1, max: 20)                  │")
    print("└─────────────────────────────────────┘")
    while True:
        try:
            val = input("  Jumlah wallet → ").strip()
            count = int(val)
            if 1 <= count <= 20:
                return count
            print(f"  ❌ Harus antara 1-20, input lagi...")
        except ValueError:
            print(f"  ❌ Input angka saja...")


def generate_wallet() -> dict:
    """Generate 1 wallet baru dengan mnemonic BIP39."""
    mnemo = Mnemonic("english")
    mnemonic_phrase = mnemo.generate(strength=128)
    acct = Account.from_mnemonic(mnemonic_phrase)
    return {
        "address": acct.address,
        "private_key": acct.key.hex(),
        "mnemonic": mnemonic_phrase,
        "delegated": False,
        "mint_done": False,
        "fee_returned": False,
    }


def send_eth(w3: Web3, sender_key: str, to_address: str, amount_eth: float) -> str:
    """Kirim ETH dari main wallet ke target address."""
    sender = Account.from_key(sender_key)
    nonce = w3.eth.get_transaction_count(sender.address, "pending")

    latest = w3.eth.get_block("latest")
    base_fee = latest["baseFeePerGas"]
    max_priority = w3.to_wei(1.5, "gwei")
    max_fee = base_fee * 2 + max_priority
    amount_wei = w3.to_wei(amount_eth, "ether")

    tx = {
        "type": 2,
        "chainId": w3.eth.chain_id,
        "nonce": nonce,
        "to": Web3.to_checksum_address(to_address),
        "value": amount_wei,
        "gas": 21000,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": max_priority,
    }

    signed = w3.eth.account.sign_transaction(tx, sender_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


def main():
    parser = argparse.ArgumentParser(description="Generate & fund minter wallets")
    parser.add_argument("--count", type=int, default=None,
                        help="Jumlah wallet (1-20). Kalau tidak diisi, akan ditanya interaktif.")
    args = parser.parse_args()

    # Interaktif kalau --count tidak diisi
    if args.count is None:
        count = ask_wallet_count()
    else:
        count = args.count
        if count < 1 or count > 20:
            print("❌ Count harus antara 1-20")
            sys.exit(1)

    cfg = load_config()
    w3 = Web3(Web3.HTTPProvider(cfg["rpc_url"]))

    if not w3.is_connected():
        print(f"❌ Gagal connect ke RPC!")
        sys.exit(1)

    main_acct = Account.from_key(cfg["private_key"])
    main_balance = w3.eth.get_balance(main_acct.address) / 1e18
    fee_per_wallet = cfg.get("fee_per_wallet_eth", 0.005)
    total_needed = fee_per_wallet * count

    print(f"\n{'='*55}")
    print(f"  STEP 1 — Generate & Fund Minter Wallets")
    print(f"{'='*55}")
    print(f"Main wallet : {main_acct.address}")
    print(f"Balance     : {main_balance:.6f} ETH")
    print(f"Wallets     : {count} wallet")
    print(f"Fee/wallet  : {fee_per_wallet} ETH")
    print(f"Total needed: {total_needed:.4f} ETH")

    if main_balance < total_needed + 0.002:
        print(f"\n❌ Balance tidak cukup! Butuh minimal {total_needed + 0.002:.4f} ETH")
        sys.exit(1)

    # Konfirmasi sebelum lanjut
    print(f"\n⚡ Siap generate {count} wallet dan kirim total {total_needed:.4f} ETH?")
    confirm = input("  Lanjut? (y/n) → ").strip().lower()
    if confirm != "y":
        print("  Dibatalkan.")
        sys.exit(0)

    # Load existing wallets jika ada
    existing_wallets = []
    if os.path.exists(WALLETS_FILE):
        try:
            with open(WALLETS_FILE) as f:
                content = f.read().strip()
                if content:
                    existing_wallets = json.loads(content)
                    print(f"\n⚠  wallets.json sudah ada ({len(existing_wallets)} wallet) — akan ditambah {count} wallet baru")
                else:
                    print(f"\n⚠  wallets.json kosong — akan dibuat baru")
        except json.JSONDecodeError:
            print(f"\n⚠  wallets.json corrupt — akan dibuat ulang")
            existing_wallets = []

    # Generate wallets
    print(f"\n📝 Generating {count} wallet baru...")
    new_wallets = []
    for i in range(count):
        w = generate_wallet()
        new_wallets.append(w)
        print(f"  [{i+1}] {w['address']}")

    # Simpan dulu sebelum kirim (antisipasi error di tengah)
    all_wallets = existing_wallets + new_wallets
    with open(WALLETS_FILE, "w") as f:
        json.dump(all_wallets, f, indent=2)
    print(f"\n✅ {len(new_wallets)} wallet disimpan ke {WALLETS_FILE}")

    # Kirim fee ke masing-masing wallet baru
    print(f"\n💸 Mengirim {fee_per_wallet} ETH ke tiap wallet baru...")
    for i, w in enumerate(new_wallets):
        try:
            print(f"  [{i+1}] Kirim ke {w['address']}...", end=" ", flush=True)
            tx_hash = send_eth(w3, cfg["private_key"], w["address"], fee_per_wallet)
            print(f"✅ https://etherscan.io/tx/{tx_hash}")
            all_wallets[len(existing_wallets) + i]["fund_tx"] = tx_hash
            time.sleep(1)
        except Exception as e:
            print(f"❌ Gagal: {e}")

    # Update wallets.json dengan fund_tx
    with open(WALLETS_FILE, "w") as f:
        json.dump(all_wallets, f, indent=2)

    print(f"\n{'='*55}")
    print(f"✅ STEP 1 SELESAI!")
    print(f"   {len(new_wallets)} wallet di-generate dan di-fund")
    print(f"   Tunggu ~15 detik lalu jalankan:")
    print(f"   python step2_delegate.py")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
