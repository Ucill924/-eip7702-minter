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
gork_minter/
├── main_wallet_config.json     ← config main wallet (edit ini dulu!)
├── wallets.json                ← auto-generated, simpan data minter wallets
│
├── step1_generate_wallets.py   ← generate wallet baru + funding dari main
├── step2_delegate.mjs          ← EIP-7702 delegation ke MintDelegate GORK (Node.js)
└── mint_gork.py                ← auto SIWE login + mint loop paralel via MCP relay
```

---

## ⚙️ Requirements

### Python
```bash
pip install web3 eth-account mnemonic rlp eth-keys requests
```

### Node.js (untuk step2 delegation)
```bash
npm install viem
```

---

## 🚀 Quick Start

### 1. Edit `main_wallet_config.json`

```json
{
  "private_key": "0xYOUR_MAIN_WALLET_PRIVATE_KEY",
  "rpc_url": "https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY",
  "fee_per_wallet_eth": 0.005,
  "return_fee_after_mint": true
}
```

> ⚠️ Main wallet **TIDAK** akan di-delegate ke manapun. Hanya sebagai pengirim fee saja.

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
```

Atau langsung pakai flag:
```bash
python step1_generate_wallets.py --count 3
```

> ⏳ Tunggu ~15-30 detik setelah TX funding confirm sebelum lanjut ke step 2.

---

### Step 2 — EIP-7702 Delegation ke MintDelegate GORK

```bash
node step2_delegate.mjs
```

Pastikan di `step2_delegate.mjs` delegate contract sudah diubah ke MintDelegate GORK:

```javascript
const DELEGATE_CONTRACT = '0x9941eF1344209F5c7e554eeAC18C9be5dCD9074F';
```

- Sign & broadcast EIP-7702 type-4 TX via **viem** (`executor: 'self'`)
- Target delegate: `0x9941eF1344209F5c7e554eeAC18C9be5dCD9074F` (MintDelegate GORK)
- Update status `delegated: true` di `wallets.json`
- Verifikasi via `Validity: True` di Etherscan tab Authorizations

> ℹ️ Delegation pakai Node.js + viem karena Python `eth-account` tidak support `executor: 'self'` yang dibutuhkan untuk EIP-7702 nonce handling yang benar.

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
  [2] Loop terus sampai 3 slot × habis atau Ctrl+C
  Pilih mode (1/2) → 2

  Mode     : Loop sampai max
  Lanjut? (y/n) → y
```

Output saat berjalan:

```
==================================================
  LOOP #1 — 2026-05-11 07:03:13
  Wallet: 0x1d30FF222FA4770D1C3Ff0af851cdBbF2f3AdF1c
==================================================
>>> check_gork_status
  founder_nfts: 1 | mints_used: 1 | mints_remaining: 9
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
    ├─► Generate N wallet baru          [step1]
    │
    └─► Kirim fee_per_wallet_eth ke tiap wallet  [step1]

wallet_1 ... wallet_N
    │
    ├─► EIP-7702 delegation ke MintDelegate      [step2 - Node.js]
    │       DELEGATE_CONTRACT = 0x9941eF13...
    │       signAuthorization(executor: 'self')
    │       → Validity: True ✅
    │
    └─► Auto SIWE login + Mint via MCP           [mint_gork.py]
            get nonce → sign SIWE → bind_token
            → MCP session → mint loop paralel

[Ctrl+C atau max 10 slot]
    └─► Optional: return sisa ETH ke main wallet
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
| Claim | Setelah 21,000 mints terpenuhi via `hook.claim()` |

---

## 📝 Notes

- `wallets.json` berisi **private key & mnemonic** — **jangan di-commit ke GitHub!**
- Pastikan `.gitignore` sudah include `wallets.json` dan `main_wallet_config.json`
- Tiap wallet butuh minimal `0.005 ETH` untuk gas delegation + mint fees
- Auto SIWE login berlaku 24 jam — script auto refresh setelah 20 jam
- Step2 aman dijalankan ulang — otomatis skip wallet yang sudah delegated
- `LOOP_DELAY` default 60 detik — ubah di `mint_gork.py` sesuai kebutuhan

---

## 🔧 Troubleshooting

| Error | Solusi |
|-------|--------|
| `Validity: False` di Etherscan | Pastikan pakai `node step2_delegate.mjs` dengan contract `0x9941eF13...` |
| `delegated=False` saat login | Jalankan step2 ulang, cek TX Etherscan |
| `ETH tidak cukup` | Top up wallet atau naikkan `fee_per_wallet_eth` |
| `Session expired` | Script auto re-login, tunggu saja |
| `slots remaining: 0` | Wallet sudah max 10 slot |
| `wallets.json not found` | Jalankan step1 dulu |

---


```
