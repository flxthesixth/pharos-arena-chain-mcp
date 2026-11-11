# Portfolio Assistant — verifikasi VPS

Status per 2026-11-11: implementasi CLI read-only dan video review LIMITED tersedia. Build/share ai.pharos.xyz, deploy, publikasi source, dan submit belum terbukti selesai. Penerimaan video bukan izin publikasi atau kelulusan security/requirement.

## Jalankan

```bash
cd /home/ubuntu/pharos-arena-chain-mcp
python3 -m unittest discover -p 'test_pharos_portfolio_box3_20261110.py' -v
python3 pharos_portfolio_box3_20261110.py 0xa3a331bd8ad8122c3fce2a1ea2de4d0dde267bac 'Where is my USDC?'
```

Python stdlib saja. Tiap permintaan RPC timeout 15 detik. Angka berupa unit dasar mentah, bukan USD; tidak mengasumsikan harga atau decimals. Wallet contoh berasal dari log publik RockawayX, bukan wallet pemilik/pengguna dan bukan alamat nol.

## Pemeriksaan requirement

Sumber: halaman publik [Portfolio Assistant](https://pharos-agent-arena.vercel.app/tasks/portfolio-assistant). Teks publik tersimpan di `evidence/portfolio-assistant/public-requirements.json`; katalog lokal bukan dependency publik.

| Requirement | Hasil teramati |
|---|---|
| Minimal dua protokol/vault dan saldo wallet | Kedua vault berhasil dibaca pada block **22655612**. Wallet USDC **1974365593**; RockawayX shares **1981531086279423740862327**, underlying **2000004445823**; SharpByte shares/underlying **0**. Total USDC mentah **2001978811416**. Ini membuktikan dua pembacaan vault, bukan dua posisi nonzero. |
| Minimal lima tipe pertanyaan NL | Tujuh intent lolos test dan replay respons RPC historis terpaku: balances, positions, vaults, exposure, compare, largest, earnings. Pertanyaan contoh lengkap tersimpan dalam `evidence/portfolio-assistant/questions-pinned-replay.json`. Replay bukan tujuh snapshot jaringan baru. |
| Sumber contract/block tiap angka | Setiap nilai saldo, shares, underlying, dan total memuat `contract`, `block`, `method`; total merujuk komponen terpisah. PROS menggunakan sentinel alamat nol sebagai penanda native, bukan contract. |
| Tidak menebak saat gagal/tidak tahu | Earnings/yield selalu `unknown` tanpa histori. Test membuktikan kegagalan vault membuat underlying/total/comparison/largest `unknown`. Snapshot awal parsial juga disimpan, bukan dibuang. |
| Read-only | Audit AST dan trace RPC hanya menemukan eth_chainId, eth_blockNumber, eth_getCode, eth_call, eth_getBalance. Tidak ada signer, private key, approval, atau transaction. |

## Bukti build lokal

- `evidence/portfolio-assistant/tests.txt`: catatan historis **6 tests PASS**, bukan jumlah test source sekarang. Source sekarang memiliki **11 tests**, jalankan perintah di atas.
- `evidence/portfolio-assistant/live-snapshot.json` dan `evidence/portfolio-assistant/rpc-trace.json`: **17** respons RPC historis, chain **1672**, satu block terpaku.
- `evidence/portfolio-assistant/questions-pinned-replay.json`: tujuh jawaban historis memakai respons sama. Bukan kesetaraan JSON penuh dengan source sekarang: method total exposure berubah; jawaban largest sekarang menyertakan saldo wallet. Tidak ditemukan selisih nilai finansial pada field bersama.
- `evidence/portfolio-assistant/cli-smoke.json`: eksekusi CLI historis exit **0**, block **22655655**, total USDC mentah **2001978906730**; nilai berubah sesuai block.
- `evidence/portfolio-assistant/validation.txt`: ringkasan validasi historis. Ruff, mypy, bandit tidak dijalankan pada pemeriksaan tersebut; tidak ada install.
- `evidence/portfolio-assistant/reconciliation/check.py`: pemeriksaan offline source sekarang terhadap respons tersimpan, numeric/citation, dan integritas bukti. Hasil tersimpan di `evidence/portfolio-assistant/reconciliation/results.json`; bukan RPC baru atau autentikasi capture.

Rollback historis lokal tidak termasuk dependency publik README ini. Source/test Portfolio masih kandidat publikasi, bukan bukti sudah tersedia di default branch.

Perubahan minimal: regex earnings kini mengenali `earned` dan `returns`; regression test gagal sebelum fix, lalu lolos. Tidak mengubah file tugas lain.

## Sumber deployment dan batas bukti

Konfigurasi memakai kandidat deployment pihak ketiga, **bukan deployment resmi yang terverifikasi**:

- RockawayX: `0x047cD0a91E9B92ED979189a6C8A120bf280f02E5`
- SharpByte: `0x15c25ED222fc498f672af5c3adb5ED0a96E1AFf1`
- Asset USDC: `0xC879C018dB60520F4355C26eD1a6D572cdAC1815`

Read-only `name()` mengembalikan `RockawayX USDC` dan `SharpByte USDC Pharos Ecosystem`; `asset()` kedua vault sama dengan asset konfigurasi. Ini memverifikasi identitas yang dilaporkan contract, bukan keaslian resmi, audit, keamanan, redeemability, atau kepemilikan pengguna. URL discovery awal deployment tidak tersedia; jangan mengklaim provenance resmi. Wallet contoh muncul pada log RockawayX block `0x159ad5f`, transaksi `0x3118c7be336dbdc350526489478b55fb34d2b39d1ffb4a4c2b303cc6d8f96f22`.

RPC sempat HTTP 429; snapshot pertama jujur parsial. Pengulangan berjarak satu detik berhasil penuh. Tidak menambah retry otomatis; bila trafik meningkat, tambahkan throttling sesuai limit provider. Log RPC dibatasi rentang 1000 block. Tidak melakukan scan histori tanpa batas.

Parser NL berbasis pola English, bukan pemahaman arbitrer. Harga USD, histori profit, reward, protokol lain, multibahasa, dan reorg/block-hash finality belum didukung. Test negatif input mencakup alamat invalid, pertanyaan unsupported, dan non-text; bukan audit fuzz lengkap.

Observasi historis akses anonim menampilkan **Sign in with GitHub**. Metadata per 2026-11-11 di `videos/portfolio-assistant.json` kemudian mencatat akun **flxthesixth**, **UNSUBMITTED**, dan required proof URL kosong; bukan autentikasi baru pada pemeriksaan offline ini. [Video dan batas penerimaan](videos/README.md) mempertahankan Dry-Run serta Portfolio sebagai delta publikasi tertunda. Path `video-demos/` pada metadata merupakan provenance lokal, bukan dependency publik atau proof reviewer-openable.

Video r1 diterima sebatas LIMITED, SHA-256 `b16168dc560578acf69581dc0c3b98729f803b767cd851bf58f90d276027c578`. Capture ringkasan block **22707754** mencatat total **2002137514272**, bukan snapshot awal block **22655612**. Nilai berasal dari block berbeda; jangan menyamakan angka lintas block atau mengklaim rekaman kontinu. Driver lokal cocok hash manifest r1, tetapi baseline driver remote saat capture tidak terautentikasi. Assertion driver hilang dengan `python -O`; security/provenance HOLD tetap blocking dan tidak dihapus oleh penerimaan LIMITED. Driver/media tidak diperbaiki atau dirender ulang pada delta dokumentasi ini.

Build/share proof publik asli dan publikasi source tetap gate terpisah. Review independen baru wajib sebelum publikasi; verifikasi akses anonim dan requirement wajib sebelum submit pertama berizin. Tidak membuat transaksi atau mengganti proof dengan URL repo/video.
