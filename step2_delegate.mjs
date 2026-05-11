

import { createPublicClient, createWalletClient, http } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { mainnet } from 'viem/chains';
import { readFileSync, writeFileSync } from 'fs';

const DELEGATE_CONTRACT = '0x9941eF1344209F5c7e554eeAC18C9be5dCD9074F';
const WALLETS_FILE = 'wallets.json';
const CONFIG_FILE  = 'main_wallet_config.json';

function loadConfig() {
  return JSON.parse(readFileSync(CONFIG_FILE, 'utf8'));
}

function loadWallets() {
  return JSON.parse(readFileSync(WALLETS_FILE, 'utf8'));
}

function saveWallets(wallets) {
  writeFileSync(WALLETS_FILE, JSON.stringify(wallets, null, 2));
}

async function checkDelegation(publicClient, address) {
  try {
    const delegation = await publicClient.getDelegation({ address });
    return delegation ? delegation.toLowerCase() : null;
  } catch {
    // fallback: cek via getCode
    const code = await publicClient.getCode({ address });
    if (code && code.startsWith('0xef0100') && code.length >= 46) {
      return '0x' + code.slice(8, 48).toLowerCase();
    }
    return null;
  }
}

async function delegateWallet(wallet, rpcUrl) {
  const privateKey = wallet.private_key.startsWith('0x') 
    ? wallet.private_key 
    : '0x' + wallet.private_key;

  const account = privateKeyToAccount(privateKey);

  const publicClient = createPublicClient({
    chain: mainnet,
    transport: http(rpcUrl),
  });

  const walletClient = createWalletClient({
    account,
    chain: mainnet,
    transport: http(rpcUrl),
  });

  // Cek balance
  const balance = await publicClient.getBalance({ address: account.address });
  const balEth = Number(balance) / 1e18;
  console.log(`    💰 Balance: ${balEth.toFixed(6)} ETH`);

  if (balEth < 0.0005) {
    console.log(`    ⚠ Balance terlalu rendah — skip`);
    return false;
  }

  // Cek existing delegation
  const current = await checkDelegation(publicClient, account.address);
  if (current && current === DELEGATE_CONTRACT.toLowerCase()) {
    console.log(`    ✅ Sudah terdelegasi ke FeedDelegate`);
    return true;
  }
  if (current) {
    console.log(`    ⚠ Delegasi ke contract lain: ${current} — akan di-update`);
  }

  // Sign authorization — viem handle nonce otomatis dengan executor: 'self'
  console.log(`    📝 Signing authorization...`);
  const authorization = await walletClient.signAuthorization({
    account,
    contractAddress: DELEGATE_CONTRACT,
    executor: 'self',
  });

  console.log(`    ✅ Authorization signed | nonce=${authorization.nonce} yParity=${authorization.yParity}`);

  // Broadcast type-4 TX
  console.log(`    📡 Broadcasting TX...`);
  const hash = await walletClient.sendTransaction({
    account,
    authorizationList: [authorization],
    to: account.address,
    data: '0x',
    value: 0n,
  });

  console.log(`    📡 TX: https://etherscan.io/tx/${hash}`);
  console.log(`    ⏳ Menunggu konfirmasi...`);

  const receipt = await publicClient.waitForTransactionReceipt({ hash });

  // Verifikasi
  const updated = await checkDelegation(publicClient, account.address);
  if (!updated || updated !== DELEGATE_CONTRACT.toLowerCase()) {
    console.log(`    ❌ Delegation gagal. Current: ${updated ?? 'none'}`);
    return false;
  }

  console.log(`    ✅ Delegated! Block: ${receipt.blockNumber}`);
  console.log(`    ✅ Verifikasi: ${account.address} → ${updated}`);
  return true;
}

async function main() {
  console.log(`\n${'='.repeat(55)}`);
  console.log(`  STEP 2 — EIP-7702 Delegation (viem)`);
  console.log(`${'='.repeat(55)}`);

  const cfg     = loadConfig();
  const wallets = loadWallets();

  console.log(`Total wallets loaded: ${wallets.length}`);
  console.log(`RPC: ${cfg.rpc_url}\n`);

  const publicClient = createPublicClient({
    chain: mainnet,
    transport: http(cfg.rpc_url),
  });

  // Cek status delegation semua wallet dulu
  console.log(`🔍 Cek status delegation...`);
  for (let i = 0; i < wallets.length; i++) {
    const w = wallets[i];
    const current = await checkDelegation(publicClient, w.address);
    if (current && current === DELEGATE_CONTRACT.toLowerCase()) {
      wallets[i].delegated = true;
      console.log(`  [${i+1}] ${w.address} — ✅ Sudah delegated`);
    } else {
      wallets[i].delegated = false;
      console.log(`  [${i+1}] ${w.address} — ⬜ ${current ? `→ ${current}` : 'Belum'}`);
    }
  }
  saveWallets(wallets);

  // Delegate yang belum
  const toDo = wallets.filter(w => !w.delegated);
  console.log(`\n📝 ${toDo.length} wallet perlu di-delegate...`);

  if (toDo.length === 0) {
    console.log('✅ Semua wallet sudah terdelegasi!');
  } else {
    for (let i = 0; i < wallets.length; i++) {
      if (wallets[i].delegated) continue;
      console.log(`\n  [${i+1}] Delegating ${wallets[i].address}...`);
      const success = await delegateWallet(wallets[i], cfg.rpc_url);
      wallets[i].delegated = success;
      saveWallets(wallets);
      if (success && i < wallets.length - 1) {
        await new Promise(r => setTimeout(r, 3000));
      }
    }
  }

  const count = wallets.filter(w => w.delegated).length;
  console.log(`\n${'='.repeat(55)}`);
  console.log(`✅ STEP 2 SELESAI!`);
  console.log(`   ${count}/${wallets.length} wallet terdelegasi`);
  if (count > 0) console.log(`   Jalankan: python step3_mint.py`);
  console.log(`${'='.repeat(55)}\n`);
}

main().catch(err => {
  console.error('\n❌ Error:', err.message || err);
  process.exit(1);
});
