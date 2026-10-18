# flapjax-verify

Read-only on-chain verifier for **FLAPJAX** on BNB Chain. Standard library only — no dependencies, no API keys, no wallet, nothing to install.

Every number FLAPJAX publishes (supply, treasury balance, pool price, "we paid this agent") can be re-derived from BNB Chain by anyone. This tool does that derivation in four commands, so you never have to trust a screenshot.

```
FLAPJAX   0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df
treasury  0x7C34E9e21eE28A49Ff0b84B61774119E6633359f
pool      0xca93ec685b8623688e6b236f9068034b298c2150   FLAPJAX/WBNB, 1% (PancakeSwap V3)
```

## Install

Nothing to install. Python 3.8+ and outbound HTTPS.

```bash
git clone https://github.com/ciperx/flapjax-verify
cd flapjax-verify
python3 flapjax_verify.py state
```

## Commands

### `state` — token, treasury and pool snapshot

```bash
$ python3 flapjax_verify.py state --bnb-usd 720
block            128,292,650
token            FLAPJAX 0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df
decimals         18
total supply     44,444,444,444 FLAPJAX
treasury         0x7C34E9e21eE28A49Ff0b84B61774119E6633359f
treasury holds   268,863,297.483780 FLAPJAX (0.60% of supply)
pool             0xca93ec685b8623688e6b236f9068034b298c2150 (fee 1.00%)
pool reserves    20,118,566,480 FLAPJAX / 6.907678 WBNB
tick             -215906
price            2,377,947,077 FLAPJAX per WBNB
price (usd)      $3.028e-07 per FLAPJAX @ BNB $720.00
fdv (usd)        $13,456.99
pool tvl (usd)   $9,947.06
```

Price comes from the pool's `slot0()` sqrt-price, not from an indexer. Pool reserves are `balanceOf(pool)` on both tokens, so the TVL line is the real depth a seller would trade against — it is not "liquidity" in the market-maker sense.

### `tx` — did this transaction actually move FLAPJAX?

```bash
$ python3 flapjax_verify.py tx 0x8e4c8cb7d5927afd9e6c4243dd13e726dcfbd4ae900578566162878011feb775
tx               0x8e4c8cb7d5927afd9e6c4243dd13e726dcfbd4ae900578566162878011feb775
block            128,267,486 at 2026-10-18T00:37:02Z
status           success
from             0x7c34e9e21ee28a49ff0b84b61774119e6633359f
to               0x90c8889f428f9ebb77bb8f15cad3a50a9ac680df
flapjax moves    1
        100,000.000000  0x7c34e9e2..33359f -> 0x226ea74d..3b2588  [FROM TREASURY]
total moved      100,000.000000 FLAPJAX
```

The `[FROM TREASURY]` tag is what makes a payout claim checkable. A transaction hash alone proves nothing — it can be a call that reverted, or an unrelated token. This reads the receipt, filters logs to the FLAPJAX contract, decodes the `Transfer` event, and says who sent what to whom.

### `transfers` — every FLAPJAX transfer in a block range

```bash
$ python3 flapjax_verify.py transfers 128265000 128270000
1 transfer(s) in blocks 128,265,000-128,270,000
  128,267,486      100,000.000000  0x7c34e9e2..33359f -> 0x226ea74d..3b2588
treasury out     100,000.000000 FLAPJAX
treasury in      0.000000 FLAPJAX
```

Add `--treasury-only` to filter on the sender being the treasury at the RPC level (cheaper on wide ranges).

### `receipt` — a buyback-style receipt for a block range

```bash
$ python3 flapjax_verify.py receipt 128260000 128292000 --bnb-usd 720
receipt          blocks 128,260,000-128,292,000
transfers        9
treasury paid    1,650,000.000000 FLAPJAX in 7 transfer(s)
treasury got     0.000000 FLAPJAX in 0 transfer(s)
net out          1,650,000.000000 FLAPJAX
treasury holds   268,863,297.483780 FLAPJAX
price            2,377,947,077 FLAPJAX per WBNB
paid (usd)       $0.4996 @ BNB $720.00
re-derive this   same block range on any BSC node; no trust required
```

This is the shape a payout receipt should take: a block range, the transfers in it, what left the treasury, what came back, and what the treasury still holds. Anyone can re-run the same range and get the same answer.

## Design notes

**`eth_getLogs` is chunked at 1000 blocks.** Most public BSC nodes reject wider ranges, and some reject them with an error that a naive client silently swallows into "zero transfers" — which would make a busy range look empty. Chunking keeps that failure mode off the table.

**Four RPC endpoints, rotated on failure.** Public BSC nodes rate-limit and occasionally return `null`. `rpc()` retries across the list before giving up, and exits non-zero rather than printing a zero.

**Token0 is FLAPJAX, token1 is WBNB, both 18 decimals**, so the sqrt-price ratio is the raw ratio — no decimal adjustment. If that ever changes, `pool_state()` is the one place to fix.

**Read-only.** No private keys, no signing, no approvals, no writes. Every call is `eth_call`, `eth_getLogs`, `eth_getTransactionReceipt` or `eth_blockNumber`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The unit tests cover the pure decoding paths (address padding, log decoding, price maths, block-range chunking) with no network access.

## License

MIT. Fork it, re-point the constants, verify another token.
