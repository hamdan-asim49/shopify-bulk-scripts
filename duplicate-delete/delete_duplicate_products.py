import requests
import json
import time
from datetime import datetime
import sys
import os

# Add parent directory to path to import parameters
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from parameters import SHOPIFY_STORE, ACCESS_TOKEN, API_VERSION, SHOPIFY_API_URL, SHOPIFY_GRAPHQL_URL, nzd_to_aud

def delete_product(product_id):
    """Delete a single product using GraphQL mutation"""
    mutation = """
    mutation productDelete($input: ProductDeleteInput!) {
        productDelete(input: $input) {
            deletedProductId
            userErrors {
                field
                message
            }
        }
    }
    """
    
    variables = {
        "input": {
            "id": product_id
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN
    }
    
    try:
        response = requests.post(
            SHOPIFY_GRAPHQL_URL,
            headers=headers,
            json={"query": mutation, "variables": variables},
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        if "errors" in result:
            return {"success": False, "error": result["errors"]}
        
        data = result.get("data", {}).get("productDelete", {})
        user_errors = data.get("userErrors", [])
        
        if user_errors:
            return {"success": False, "error": user_errors}
        
        return {"success": True, "deleted_id": data.get("deletedProductId")}
        
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}

def delete_products_from_file(input_file="products_to_delete.json", log_file="deletion_log.json"):
    """Delete all products listed in the input file"""
    
    # Read products to delete
    print(f"📖 Reading products from {input_file}...")
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            products = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {input_file} not found!")
        return
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {input_file}: {e}")
        return
    
    total_products = len(products)
    print(f"🗑️  Found {total_products} products to delete\n")
    
    # Confirm deletion
    print("⚠️  WARNING: This will permanently delete these products from Shopify!")
    confirmation = input(f"Type 'DELETE' to confirm deletion of {total_products} products: ")
    
    if confirmation != "DELETE":
        print("❌ Deletion cancelled.")
        return
    
    print(f"\n🚀 Starting deletion process...\n")
    
    # Track results
    deletion_log = {
        "started_at": datetime.now().isoformat(),
        "total_products": total_products,
        "successful_deletions": [],
        "failed_deletions": [],
        "completed_at": None
    }
    
    successful = 0
    failed = 0
    
    # Delete products one by one
    for idx, product in enumerate(products, 1):
        product_id = product["id"]
        title = product["title"]
        reason = product.get("reason", "N/A")
        
        print(f"[{idx}/{total_products}] Deleting: {title}")
        print(f"  ID: {product_id}")
        print(f"  Reason: {reason}")
        
        result = delete_product(product_id)
        
        if result["success"]:
            print(f"  ✅ Successfully deleted\n")
            successful += 1
            deletion_log["successful_deletions"].append({
                "id": product_id,
                "title": title,
                "reason": reason,
                "deleted_at": datetime.now().isoformat()
            })
        else:
            print(f"  ❌ Failed: {result['error']}\n")
            failed += 1
            deletion_log["failed_deletions"].append({
                "id": product_id,
                "title": title,
                "reason": reason,
                "error": str(result["error"]),
                "failed_at": datetime.now().isoformat()
            })
        
        # Rate limiting - Shopify allows 2 requests per second for GraphQL
        # Being conservative with 0.6 seconds between requests
        if idx < total_products:
            time.sleep(0.6)
        
        # Save progress every 50 products
        if idx % 50 == 0:
            deletion_log["completed_at"] = datetime.now().isoformat()
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(deletion_log, f, indent=2, ensure_ascii=False)
            print(f"💾 Progress saved to {log_file}\n")
    
    # Final summary
    deletion_log["completed_at"] = datetime.now().isoformat()
    
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(deletion_log, f, indent=2, ensure_ascii=False)
    
    print("=" * 60)
    print("📊 DELETION SUMMARY")
    print("=" * 60)
    print(f"✅ Successfully deleted: {successful}")
    print(f"❌ Failed: {failed}")
    print(f"📝 Total processed: {total_products}")
    print(f"📄 Detailed log saved to: {log_file}")
    print("=" * 60)

def preview_deletions(input_file="products_to_delete.json"):
    """Preview the products that will be deleted without actually deleting them"""
    
    print(f"📖 Reading products from {input_file}...")
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            products = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {input_file} not found!")
        return
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {input_file}: {e}")
        return
    
    total_products = len(products)
    print(f"\n🔍 Preview: {total_products} products will be deleted\n")
    
    # Show first 10 as preview
    preview_count = min(10, total_products)
    print(f"First {preview_count} products:")
    print("-" * 60)
    
    for idx, product in enumerate(products[:preview_count], 1):
        print(f"{idx}. {product['title']}")
        print(f"   ID: {product['id']}")
        print(f"   Reason: {product.get('reason', 'N/A')}")
        print(f"   Created: {product.get('created_at', 'N/A')}\n")
    
    if total_products > preview_count:
        print(f"... and {total_products - preview_count} more products")
    
    print("-" * 60)

if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("🗑️  SHOPIFY DUPLICATE PRODUCT DELETION SCRIPT")
    print("=" * 60)
    print()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--preview":
        # Preview mode
        preview_deletions()
    else:
        # Actual deletion
        delete_products_from_file()

