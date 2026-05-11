# 🧠 $GORK Minter Toolkit — gorkshit.meme

> Multi-wallet automation tool untuk mint `$GORK` Founder NFT di [gorkshit.meme](https://gorkshit.meme) via EIP-7702 delegation + Auto SIWE login + MCP relay.

---

## ✨ Features

- 🔑 Generate multi wallet baru otomatis (BIP39 mnemonic)
- 💸 Auto-funding dari main wallet ke minter wallets
- ⚡ EIP-7702 delegation otomatis via **viem** (Node.js)
- 🤖 Auto SIWE login per wallet — tidak perlu login manual
- 🔄 Mint loop paralel — semua wallet jalan bersamaan
- 📋 Semua data wallet tersimpan di `wallets.json`

---

## 📁 File Structure

```
eip7702-minter/
├── main_wallet_config.json     ← config main wallet (edit ini dulu!)
├── wallets.json                ← auto-generated, simpan data minter wallets
│
├── step1_generate_wallets.py   ← generate wallet baru + funding dari main
├── step2_delegate.mjs          ← EIP-7702 delegation ke MintDelegate GORK (Node.js)
└── mint_gork.py                ← auto SIWE login + mint loop paralel via MCP relay
```

---

## ⚙️ Requirements

### System
- Python 3.10+
- Node.js 18+

### Python dependencies
```bash
pip install web3 eth-account mnemonic rlp eth-keys requests
```

### Node.js dependencies
```bash
npm install viem
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/Ucill924/eip7702-minter.git
cd eip7702-minter

# Install Python deps
pip install web3 eth-account mnemonic rlp eth-keys requests

# Install Node deps
npm install viem
```

### 2. Edit `main_wallet_config.json`

```json
{
  "private_key": "0xYOUR_MAIN_WALLET_PRIVATE_KEY",
  "rpc_url": "https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY",
  "fee_per_wallet_eth": 0.005,
  "return_fee_after_mint": true
}
```

> ⚠️ Main wallet **TIDAK** akan di-delegate ke manapun. Hanya sebagai pengirim fee saja.

> 💡 Untuk RPC URL, daftar gratis di [Alchemy](https://alchemy.com) atau [Infura](https://infura.io)

---

### Step 1 — Generate & Fund Wallets

```bash
python step1_generate_wallets.py
```

Script akan menanyakan jumlah wallet secara interaktif:

```
┌─────────────────────────────────────┐
│   Berapa wallet minter yang dibuat?  │
│   (min: 1, max: 20)                  │
└─────────────────────────────────────┘
  Jumlah wallet → 3
  Lanjut? (y/n) → y

  [1] 0xABC... ✅ https://etherscan.io/tx/0x...
  [2] 0xDEF... ✅ https://etherscan.io/tx/0x...
  [3] 0xGHI... ✅ https://etherscan.io/tx/0x...
```

Atau langsung pakai flag:
```bash
python step1_generate_wallets.py --count 3
```

> ⏳ Tunggu ~15-30 detik setelah TX funding confirm sebelum lanjut ke step 2.

---

### Step 2 — EIP-7702 Delegation

```bash
node step2_delegate.mjs
```

Script akan otomatis:
- Cek wallet mana yang belum delegated
- Sign & broadcast EIP-7702 type-4 TX via **viem**
- Verifikasi delegation on-chain
- Update status `delegated: true` di `wallets.json`

Output yang diharapkan:
```
[1] Delegating 0xABC...
    💰 Balance: 0.004923 ETH
    ✅ Authorization signed | nonce=2
    📡 TX: https://etherscan.io/tx/0x...
    ✅ Delegated! Block: 12345678
```

Verifikasi di Etherscan — buka TX, tab **Authorizations**:
- `Validity: True` ✅ → sukses
- `Validity: False` ❌ → jalankan ulang

> ℹ️ Delegation pakai Node.js + viem karena Python `eth-account` tidak support `executor: 'self'` yang dibutuhkan EIP-7702.

---

### Step 3 — Mint $GORK

```bash
python mint_gork.py
```

Script akan tanya secara interaktif:

```
┌─────────────────────────────────────┐
│   Berapa slot yang mau di-mint?      │
│   (1 slot = 10M $GORK + 0.00111 ETH) │
│   (min: 1, max: 10)                  │
└─────────────────────────────────────┘
  Jumlah slot → 3

  Mode mint:
  [1] Sekali saja (3 slot total)
  [2] Loop terus sampai max 10 slot atau Ctrl+C
  Pilih mode (1/2) → 2

  Lanjut? (y/n) → y
```

Output saat berjalan:
```
==================================================
  LOOP #1 — 2026-05-11 07:03:13
  Wallet: 0xABC...
==================================================
>>> check_gork_status
  founder_nfts: 0 | mints_used: 0 | mints_remaining: 10
  public_pool_remaining_slots: 17620

>>> mint_gork (count=3)
  minted 3 slot(s) → 3 Founder NFT(s)
  tx: https://etherscan.io/tx/0x...

  ✓ Loop #1 done. Waiting 60s...
```

---

## 🔄 Full Flow

```
Main Wallet (tidak pernah di-delegate)
    │
    ├─► Generate N wallet baru          [step1 - Python]
    │       wallet_1, wallet_2, ..., wallet_N
    │
    └─► Kirim fee_per_wallet_eth ke tiap wallet  [step1 - Python]

wallet_1 ... wallet_N
    │
    ├─► EIP-7702 delegation ke MintDelegate      [step2 - Node.js]
    │       0x9941eF1344209F5c7e554eeAC18C9be5dCD9074F
    │       signAuthorization(executor: 'self')
    │       → Validity: True ✅
    │
    └─► Auto SIWE login + Mint via MCP relay     [mint_gork.py - Python]
            get nonce → sign SIWE message
            → POST /siwe/preauth → bind_token
            → MCP session initialize
            → mint loop paralel (tiap wallet di thread sendiri)

[Ctrl+C atau max 10 slot]
    └─► Return sisa ETH ke main wallet (opsional)
            python return_fee.py
```

---

## 💰 Economics

| Item | Detail |
|------|--------|
| Fee per slot | 0.00111 ETH |
| Max slot per wallet | 10 |
| Max ETH per wallet | 0.0111 ETH |
| Reward per slot | 1 Founder NFT + 10M $GORK claim |
| Total supply | 630,690,000,000 $GORK |
| Total slots global | 21,000 |
| Claim aktif | Setelah 21,000 mints terpenuhi via `hook.claim()` |

---

## 🔧 Troubleshooting

| Error | Solusi |
|-------|--------|
| `Validity: False` di Etherscan | Jalankan `node step2_delegate.mjs` ulang |
| `delegated=False` saat mint | Step2 belum selesai, cek TX Etherscan |
| `ETH tidak cukup` | Top up wallet atau naikkan `fee_per_wallet_eth` di config |
| `Session expired` | Script auto re-login otomatis, tunggu saja |
| `slots remaining: 0` | Wallet sudah max 10 slot |
| `wallets.json not found` | Jalankan step1 dulu |
| `JSONDecodeError` | Hapus `wallets.json` yang corrupt, jalankan step1 ulang |
| `max priority fee > max fee` | RPC bermasalah, ganti ke Alchemy/Infura |
| Node.js error `Cannot find module 'viem'` | Jalankan `npm install viem` dulu |

---



```

- Wallet minter hanya punya ETH secukupnya untuk gas — risiko minimal
- Private key tersimpan lokal di `wallets.json` — jaga file ini baik-baik

---

## 📜 Contract Addresses

| Contract | Address |
|----------|---------|
| MintDelegate | `0x9941eF1344209F5c7e554eeAC18C9be5dCD9074F` |
| GorkLaunchHook | `0x2F83f5D250e184E9b4518e6bFFbf3CAe0D7e0080` |
| Founder NFT | `0x0B0036Fe9a3Dc051F0757D1AeB67950398d92FF0` |
| $GORK Token | `0xD6d62e400C48570a972635bF4b878bA00FDA1c7E` |
| Relayer | `0xb4e5164c702363BFaBe7AAECA054652D17765ED3` |

Network: **Ethereum Mainnet (Chain ID: 1)**
