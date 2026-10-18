#!/usr/bin/env python3
"""flapjax-verify — read-only on-chain verifier for FLAPJAX (BSC).

No dependencies, no API keys, no wallet. Standard library only.

Why this exists: FLAPJAX pays agents for verifiable public work, and every
claim about that token (supply, treasury balance, pool price, whether a
payment actually happened) can be re-derived from BNB Chain by anyone.
This tool does exactly that, so a reader does not have to trust a screenshot.

Commands
    state                      token + pool + treasury snapshot
    tx <hash>                  decode a transaction, verify it moved FLAPJAX
    transfers <from> <to>      every FLAPJAX Transfer in a block range
    receipt <from> <to>        buyback-style receipt for a block range

Examples
    python3 flapjax_verify.py state
    python3 flapjax_verify.py tx 0x8e4c8cb7d5927afd9e6c4243dd13e726dcfbd4ae900578566162878011feb775
    python3 flapjax_verify.py transfers 128270000 128275000
    python3 flapjax_verify.py receipt 128270000 128290000 --bnb-usd 720

Exit codes: 0 ok, 1 rpc failure, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# --- addresses (BNB Chain mainnet, chain id 56) ------------------------------
FLAPJAX = "0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df"
TREASURY = "0x7C34E9e21eE28A49Ff0b84B61774119E6633359f"
POOL_V3 = "0xca93ec685b8623688e6b236f9068034b298c2150"  # FLAPJAX/WBNB, fee 1%
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)

RPCS = [
    "https://bsc-dataseed1.defibit.io",
    "https://bsc-dataseed1.ninicoin.io",
    "https://bsc.rpc.blxrbdn.com",
    "https://bsc-dataseed.bnbchain.org",
    "https://bsc-dataseed1.bnbchain.org",
    "https://bsc.publicnode.com",
]

Q96 = 2**96
MAX_CHUNK = 1000  # blocks per eth_getLogs call; larger windows get rejected


class RpcError(RuntimeError):
    pass


def rpc(method: str, params: list, _tries: int = 5):
    """Call an RPC method, rotating nodes on failure."""
    last = None
    for attempt in range(_tries):
        for url in RPCS:
            body = json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            ).encode()
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "flapjax-verify/1.0"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    out = json.loads(r.read())
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
                last = f"{url}: {exc}"
                continue
            if "error" in out:
                last = f"{url}: {out['error']}"
                continue
            return out["result"]
        time.sleep(0.4 * (attempt + 1))
    raise RpcError(last or "no rpc node answered")


# --- tiny ABI helpers -------------------------------------------------------
def pad(addr: str) -> str:
    return addr.lower().replace("0x", "").rjust(64, "0")


def word_to_int(hexword: str) -> int:
    return int(hexword, 16) if hexword not in ("", "0x") else 0


def call(to: str, selector: str, arg: str = "") -> int:
    data = selector + arg
    out = rpc("eth_call", [{"to": to, "data": data}, "latest"])
    return word_to_int(out)


def uint(hexstr: str) -> int:
    return int(hexstr, 16) if hexstr else 0


def fmt(n: int, decimals: int = 18, places: int = 6) -> str:
    return f"{n / 10 ** decimals:,.{places}f}"


# --- contract reads ---------------------------------------------------------
def token_state() -> dict:
    supply = call(FLAPJAX, "0x18160ddd")  # totalSupply()
    decimals = call(FLAPJAX, "0x313ce567")  # decimals()
    treasury = call(FLAPJAX, "0x70a08231", pad(TREASURY))  # balanceOf(treasury)
    return {
        "symbol": "FLAPJAX",
        "address": FLAPJAX,
        "decimals": decimals,
        "total_supply_raw": supply,
        "total_supply": supply / 10**decimals,
        "treasury": TREASURY,
        "treasury_raw": treasury,
        "treasury_balance": treasury / 10**decimals,
        "treasury_share_pct": (treasury / supply * 100) if supply else 0.0,
    }


def pool_state() -> dict:
    """slot0() gives sqrtPriceX96 and the active tick."""
    raw = rpc("eth_call", [{"to": POOL_V3, "data": "0x3850c7bd"}, "latest"])
    h = raw.replace("0x", "")
    sqrt_price = int(h[0:64], 16)
    tick = int(h[64:128], 16)
    if tick >= 2**255:
        tick -= 2**256
    fj_reserve = call(FLAPJAX, "0x70a08231", pad(POOL_V3))
    wbnb_reserve = call(WBNB, "0x70a08231", pad(POOL_V3))
    # token0 = FLAPJAX, token1 = WBNB, both 18 decimals
    wbnb_per_fj = (sqrt_price / Q96) ** 2
    fj_per_wbnb = (1 / wbnb_per_fj) if wbnb_per_fj else 0.0
    return {
        "pool": POOL_V3,
        "fee_bps": 100,
        "sqrt_price_x96": sqrt_price,
        "tick": tick,
        "flapjax_reserve": fj_reserve / 1e18,
        "wbnb_reserve": wbnb_reserve / 1e18,
        "flapjax_per_wbnb": fj_per_wbnb,
        "wbnb_per_flapjax": wbnb_per_fj,
    }


def head_block() -> int:
    return uint(rpc("eth_blockNumber", []))


# --- logs -------------------------------------------------------------------
def get_logs(address: str, topics: list, start: int, end: int) -> list:
    """eth_getLogs over a range, chunked to MAX_CHUNK blocks."""
    hits, cur = [], start
    while cur <= end:
        to = min(cur + MAX_CHUNK - 1, end)
        hits += rpc(
            "eth_getLogs",
            [{"address": address, "fromBlock": hex(cur), "toBlock": hex(to), "topics": topics}],
        )
        cur = to + 1
        time.sleep(0.05)  # stay under public-node rate limits
    return hits


def decode_transfer(log: dict) -> dict:
    topics = log["topics"]
    return {
        "block": uint(log["blockNumber"]),
        "tx": log["transactionHash"],
        "from": "0x" + topics[1][-40:],
        "to": "0x" + topics[2][-40:],
        "value_raw": uint(log["data"]),
        "value": uint(log["data"]) / 1e18,
    }


def transfers(start: int, end: int, only_treasury: bool = False) -> list:
    topics = [TRANSFER_TOPIC]
    if only_treasury:
        topics.append("0x" + pad(TREASURY))
    logs = get_logs(FLAPJAX, topics, start, end)
    return [decode_transfer(l) for l in logs]


# --- commands ---------------------------------------------------------------
def cmd_state(args) -> int:
    t = token_state()
    p = pool_state()
    bnb_usd = args.bnb_usd
    print(f"block            {head_block():,}")
    print(f"token            {t['symbol']} {t['address']}")
    print(f"decimals         {t['decimals']}")
    print(f"total supply     {t['total_supply']:,.0f} FLAPJAX")
    print(f"treasury         {t['treasury']}")
    print(f"treasury holds   {t['treasury_balance']:,.6f} FLAPJAX ({t['treasury_share_pct']:.2f}% of supply)")
    print(f"pool             {p['pool']} (fee {p['fee_bps'] / 100:.2f}%)")
    print(f"pool reserves    {p['flapjax_reserve']:,.0f} FLAPJAX / {p['wbnb_reserve']:.6f} WBNB")
    print(f"tick             {p['tick']}")
    print(f"price            {p['flapjax_per_wbnb']:,.0f} FLAPJAX per WBNB")
    if bnb_usd:
        usd = p["wbnb_per_flapjax"] * bnb_usd
        print(f"price (usd)      ${usd:.3e} per FLAPJAX @ BNB ${bnb_usd:,.2f}")
        print(f"fdv (usd)        ${t['total_supply'] * usd:,.2f}")
        print(f"pool tvl (usd)   ${p['wbnb_reserve'] * bnb_usd * 2:,.2f}")
    else:
        print("price (usd)      pass --bnb-usd <price> to convert")
    return 0


def cmd_tx(args) -> int:
    h = args.hash if args.hash.startswith("0x") else "0x" + args.hash
    receipt = rpc("eth_getTransactionReceipt", [h])
    if not receipt:
        print(f"transaction {h} not found", file=sys.stderr)
        return 1
    tx = rpc("eth_getTransactionByHash", [h])
    status = uint(receipt["status"])
    block = uint(receipt["blockNumber"])
    blk = rpc("eth_getBlockByNumber", [hex(block), False])
    when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(uint(blk["timestamp"])))
    print(f"tx               {h}")
    print(f"block            {block:,} at {when}")
    print(f"status           {'success' if status == 1 else 'REVERTED'}")
    print(f"from             {tx['from']}")
    print(f"to               {tx.get('to')}")
    moved = [decode_transfer(l) for l in receipt["logs"] if l["address"].lower() == FLAPJAX.lower()
             and l["topics"] and l["topics"][0] == TRANSFER_TOPIC]
    if not moved:
        print("flapjax moves    none (this tx did not transfer FLAPJAX)")
        return 0
    print(f"flapjax moves    {len(moved)}")
    for m in moved:
        tag = ""
        if m["from"].lower() == TREASURY.lower():
            tag = "  [FROM TREASURY]"
        if m["to"].lower() == TREASURY.lower():
            tag = "  [TO TREASURY]"
        print(f"  {m['value']:>20,.6f}  {m['from']} -> {m['to']}{tag}")
    total = sum(m["value"] for m in moved)
    print(f"total moved      {total:,.6f} FLAPJAX")
    return 0


def cmd_transfers(args) -> int:
    rows = transfers(args.start, args.end, only_treasury=args.treasury_only)
    if not rows:
        print(f"no FLAPJAX transfers in blocks {args.start:,}-{args.end:,}")
        return 0
    print(f"{len(rows)} transfer(s) in blocks {args.start:,}-{args.end:,}")
    out = 0.0
    inn = 0.0
    for r in rows:
        if r["from"].lower() == TREASURY.lower():
            out += r["value"]
        if r["to"].lower() == TREASURY.lower():
            inn += r["value"]
        print(f"  {r['block']:,}  {r['value']:>18,.6f}  {r['from'][:10]}..{r['from'][-6:]} -> {r['to'][:10]}..{r['to'][-6:]}")
    print(f"treasury out     {out:,.6f} FLAPJAX")
    print(f"treasury in      {inn:,.6f} FLAPJAX")
    return 0


def cmd_receipt(args) -> int:
    rows = transfers(args.start, args.end)
    out = [r for r in rows if r["from"].lower() == TREASURY.lower()]
    inn = [r for r in rows if r["to"].lower() == TREASURY.lower()]
    paid = sum(r["value"] for r in out)
    received = sum(r["value"] for r in inn)
    t = token_state()
    p = pool_state()
    print(f"receipt          blocks {args.start:,}-{args.end:,}")
    print(f"transfers        {len(rows)}")
    print(f"treasury paid    {paid:,.6f} FLAPJAX in {len(out)} transfer(s)")
    print(f"treasury got     {received:,.6f} FLAPJAX in {len(inn)} transfer(s)")
    print(f"net out          {paid - received:,.6f} FLAPJAX")
    print(f"treasury holds   {t['treasury_balance']:,.6f} FLAPJAX")
    print(f"price            {p['flapjax_per_wbnb']:,.0f} FLAPJAX per WBNB")
    if args.bnb_usd:
        usd = p["wbnb_per_flapjax"] * args.bnb_usd
        print(f"paid (usd)       ${paid * usd:,.4f} @ BNB ${args.bnb_usd:,.2f}")
    print("re-derive this   same block range on any BSC node; no trust required")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="flapjax_verify.py",
        description="Read-only FLAPJAX (BSC) verifier: supply, treasury, pool price, transfers, receipts.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("state", help="token + pool + treasury snapshot")
    s.add_argument("--bnb-usd", type=float, default=None, help="BNB price in USD for conversions")
    s.set_defaults(fn=cmd_state)

    s = sub.add_parser("tx", help="decode and verify one transaction")
    s.add_argument("hash")
    s.set_defaults(fn=cmd_tx)

    s = sub.add_parser("transfers", help="list FLAPJAX transfers in a block range")
    s.add_argument("start", type=int)
    s.add_argument("end", type=int)
    s.add_argument("--treasury-only", action="store_true", help="only transfers sent by the treasury")
    s.set_defaults(fn=cmd_transfers)

    s = sub.add_parser("receipt", help="buyback-style receipt for a block range")
    s.add_argument("start", type=int)
    s.add_argument("end", type=int)
    s.add_argument("--bnb-usd", type=float, default=None)
    s.set_defaults(fn=cmd_receipt)

    args = ap.parse_args(argv)
    if getattr(args, "end", 0) and getattr(args, "start", 0) > args.end:
        print("error: start block is after end block", file=sys.stderr)
        return 2
    try:
        return args.fn(args)
    except RpcError as exc:
        print(f"rpc error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
