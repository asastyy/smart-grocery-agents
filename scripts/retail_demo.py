"""Offline replay by default. --live explicitly permits public catalogue calls."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from smart_grocery.retail.mcp import MCPClient
from smart_grocery.retail.report import build_retail_report
from smart_grocery.retail.snapshot import DEFAULT_CAPTURE, snapshot_provider
from smart_grocery.retail.vkusvill import VkusVillProvider
from smart_grocery.tools.grocery_provider import CartItem, ProviderUnavailable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--capture", type=Path, help="Save fresh PUBLIC responses to this directory")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cart-link", action="store_true", help="Generate a link for one normalized rice SKU; never place an order")
    args = parser.parse_args()
    if (args.capture or args.cart_link) and not args.live:
        parser.error("--capture and --cart-link require --live")
    load_dotenv(ROOT / ".env", override=False)
    if args.live:
        token = os.getenv("VKUSVILL_ACCESS_TOKEN")
        if token and args.capture:
            parser.error("Public fixture capture must run without an OAuth token")
        provider = VkusVillProvider(MCPClient(token=token), enable_cart_links=args.cart_link)
    else:
        provider = snapshot_provider(args.snapshot)
    try:
        report = build_retail_report(provider)
        report["mode"] = "live" if args.live else "snapshot"
        if args.cart_link:
            rice = provider.search_products("rice")
            if not rice:
                raise ProviderUnavailable("No normalized rice SKU for link probe")
            report["cart_link_probe"] = provider.cart_link([CartItem(product_id=rice[0].product_id, package_count=1)])
        if args.capture:
            args.capture.mkdir(parents=True, exist_ok=True)
            payload = {"source": provider.client.endpoint, "kind": "real_public_catalogue_snapshot",
                       "personalized": False, "records": provider.client.responses}
            (args.capture / "vkusvill_capture.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
            print(json.dumps({"mode": report["mode"], "offers": report["normalized_offer_count"],
                              "golden_valid": report["golden_case_strict"]["valid"], "output": str(args.output)}, ensure_ascii=False))
        else:
            print(text)
        return 0 if report["normalized_offer_count"] and not report["errors"] else 1
    except ProviderUnavailable:
        print("Retail provider unavailable. Credentials and provider response details are hidden.", file=sys.stderr)
        return 2
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
