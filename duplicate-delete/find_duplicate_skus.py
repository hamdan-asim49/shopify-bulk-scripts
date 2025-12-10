import requests
import json
from collections import defaultdict
import time
import sys
import os

# Add parent directory to path to import parameters
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from parameters import SHOPIFY_STORE, ACCESS_TOKEN, API_VERSION, SHOPIFY_API_URL, SHOPIFY_GRAPHQL_URL, nzd_to_aud

def fetch_all_products():
    """Fetch all products from Shopify using GraphQL pagination"""
    print("🔍 Fetching all products from Shopify...")
    
    query = """
    query GetAllProducts($cursor: String) {
        products(first: 250, after: $cursor) {
            edges {
                node {
                    id
                    title
                    tags
                    createdAt
                    variants(first: 100) {
                        edges {
                            node {
                                id
                                sku
                                barcode
                            }
                        }
                    }
                }
                cursor
            }
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
    """
    
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN,
    }
    
    all_products = []
    cursor = None
    page = 1
    
    while True:
        variables = {"cursor": cursor}
        
        try:
            response = requests.post(
                SHOPIFY_GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=30
            )
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching products: {e}")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            break
        
        if "errors" in data:
            print(f"❌ GraphQL errors: {data['errors']}")
            break
        
        products = data["data"]["products"]["edges"]
        all_products.extend(products)
        
        print(f"   Fetched page {page}: {len(products)} products (Total: {len(all_products)})")
        
        page_info = data["data"]["products"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        
        cursor = page_info["endCursor"]
        page += 1
        time.sleep(0.5)  # Rate limiting
    
    print(f"✅ Fetched {len(all_products)} total products\n")
    return all_products

def find_duplicates(products):
    """Find duplicate products based on SKU tag only"""
    print("🔍 Analyzing products for duplicates based on SKU tags...\n")
    
    # Track duplicates by SKU tag only
    by_sku_tag = defaultdict(list)
    products_without_sku_tag = []
    
    for product_edge in products:
        product = product_edge["node"]
        product_id = product["id"]
        title = product["title"]
        tags = product["tags"]
        created_at = product["createdAt"]
        
        # Extract SKU from tags (sku:XXX format)
        sku_from_tag = None
        for tag in tags:
            if tag.startswith("sku:"):
                sku_from_tag = tag.replace("sku:", "")
                break
        
        if sku_from_tag:
            by_sku_tag[sku_from_tag].append({
                "id": product_id,
                "title": title,
                "created_at": created_at,
                "sku_tag": sku_from_tag,
                "tags": tags
            })
        else:
            products_without_sku_tag.append({
                "id": product_id,
                "title": title,
                "created_at": created_at,
                "tags": tags
            })
    
    return {
        "by_sku_tag": {k: v for k, v in by_sku_tag.items() if len(v) > 1},
        "products_without_sku_tag": products_without_sku_tag
    }

def print_duplicate_report(duplicates):
    """Print a detailed report of duplicates"""
    print("=" * 80)
    print("DUPLICATE PRODUCTS REPORT")
    print("=" * 80)
    
    # SKU Tag Duplicates
    sku_tag_dupes = duplicates["by_sku_tag"]
    print(f"\n📌 DUPLICATES BY SKU TAG (sku:XXX)")
    print(f"   Found {len(sku_tag_dupes)} duplicate SKU tags\n")
    
    if sku_tag_dupes:
        for sku, products in sku_tag_dupes.items():
            print(f"   SKU Tag: {sku} ({len(products)} products)")
            for i, prod in enumerate(sorted(products, key=lambda x: x["created_at"]), 1):
                print(f"      {i}. {prod['title']}")
                print(f"         ID: {prod['id']}")
                print(f"         Created: {prod['created_at']}")
            print()
    else:
        print("   ✅ No duplicates found\n")
    
    print("=" * 80)

def save_duplicates_to_json(duplicates):
    """Save duplicate findings to JSON file"""
    output = {
        "summary": {
            "sku_tag_duplicates": len(duplicates["by_sku_tag"]),
        },
        "duplicates": duplicates
    }
    
    with open("duplicate_products.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Detailed duplicate report saved to 'duplicate_products.json'")

def generate_delete_script(duplicates):
    """Generate a list of product IDs that should be deleted (keeping oldest)"""
    products_to_delete = []
    
    # For SKU tag duplicates, keep the latest, delete the previous
    for sku, products in duplicates["by_sku_tag"].items():
        sorted_products = sorted(products, key=lambda x: x["created_at"])
        # Keep last (latest), delete all previous
        for prod in sorted_products[:-1]:
            products_to_delete.append({
                "id": prod["id"],
                "title": prod["title"],
                "reason": f"Duplicate SKU tag: {sku}",
                "created_at": prod["created_at"]
            })
    
    with open("products_to_delete.json", "w", encoding="utf-8") as f:
        json.dump(products_to_delete, f, indent=2, ensure_ascii=False)
    
    print(f"📝 Generated deletion list: {len(products_to_delete)} products in 'products_to_delete.json'")
    print(f"   (Kept oldest product for each duplicate set)")

def main():
    print("🚀 Starting Shopify Duplicate Product Finder\n")
    
    # Fetch all products
    products = fetch_all_products()
    
    if not products:
        print("❌ No products found or error occurred")
        return
    
    # Find duplicates
    duplicates = find_duplicates(products)
    
    # Print report
    print_duplicate_report(duplicates)
    
    # # Save to files
    save_duplicates_to_json(duplicates)
    generate_delete_script(duplicates)
    
    print("\n✅ Analysis complete!")

if __name__ == "__main__":
    main()