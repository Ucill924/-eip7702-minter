"""
return_fee.py — Return sisa ETH dari semua minter wallet ke main wallet
Bisa dijalankan kapan saja, tidak perlu step3 aktif.

Usage:
    python return_fee.py
    python return_fee.py --dry-run   # cek balance dulu tanpa kirim TX
"""

import argparse
import json
import os
import sys
import time

from eth_account import Account
from web3 import Web3

CONFIG_FILE  = "main_wallet_config.json"
WALLETS_FILE = "wallets.json"


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def load_wallets():
    with open(WALLETS_FILE) as f:
        return json.load(f)

def save_wallets(wallets):
    with open(WALLETS_FILE, "w") as f:
        json.dump(wallets, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Cek balance saja, tidak kirim TX")
    args = parser.parse_args()

    cfg     = load_config()
    wallets = load_wallets()
    w3      = Web3(Web3.HTTPProvider(cfg["rpc_url"]))

    if not w3.is_connected():
        print("❌ Gagal connect RPC"); sys.exit(1)

    main_acct = Account.from_key(cfg["private_key"])

    print(f"\n{'='*55}")
    print(f"  Return Fee → {main_acct.address}")
    print(f"{'='*55}")

    total_returned = 0

    for i, w in enumerate(wallets):
        address = w["address"]
        balance_wei = w3.eth.get_balance(Web3.to_checksum_address(address))
        balance_eth = balance_wei / 1e18

        print(f"\n[{i+1}] {address}")
        print(f"     Balance : {balance_eth:.6f} ETH")

        if balance_eth < 0.0001:
            print(f"     Status  : ⬜ Skip (balance terlalu kecil)")
            continue

        # Estimasi gas cost
        latest = w3.eth.get_block("latest")
        base_fee = latest["baseFeePerGas"]
        max_priority = w3.to_wei(1, "gwei")
        max_fee = base_fee * 2 + max_priority
        gas_cost = max_fee * 21000
        send_amount = balance_wei - gas_cost

        if send_amount <= 0:
            print(f"     Status  : ⬜ Skip (habis kena gas cost)")
            continue

        send_eth = send_amount / 1e18
        print(f"     Kirim   : {send_eth:.6f} ETH (setelah gas)")

        if args.dry_run:
            print(f"     Status  : 🔍 DRY RUN — tidak kirim TX")
            total_returned += send_eth
            continue

        # Kirim TX
        try:
            nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(address), "pending")
            tx = {
                "type": 2,
                "chainId": w3.eth.chain_id,
                "nonce": nonce,
                "to": Web3.to_checksum_address(main_acct.address),
                "value": send_amount,
                "gas": 21000,
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": max_priority,
            }
            signed = w3.eth.account.sign_transaction(tx, w["private_key"])
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hex = tx_hash.hex()

            print(f"     TX      : https://etherscan.io/tx/{tx_hex}")

            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt["status"] == 1:
                print(f"     Status  : ✅ Berhasil! Block: {receipt['blockNumber']}")
                wallets[i]["fee_returned"] = True
                wallets[i]["return_tx"] = tx_hex
                total_returned += send_eth
                save_wallets(wallets)
            else:
                print(f"     Status  : ❌ TX reverted")

        except Exception as e:
            print(f"     Status  : ❌ Error: {e}")

        time.sleep(1)

    print(f"\n{'='*55}")
    label = "DRY RUN — estimasi" if args.dry_run else "Total dikembalikan"
    print(f"  {label}: {total_returned:.6f} ETH")
    print(f"  Ke: {main_acct.address}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
