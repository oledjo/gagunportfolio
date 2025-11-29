import sys
import json
from intellinvest_sync import sync_portfolio_from_intellinvest


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <path_to_excel_file>")
        sys.exit(1)
    
    path = sys.argv[1]
    result = sync_portfolio_from_intellinvest(path)
    print(json.dumps(result, indent=2, ensure_ascii=False))

