import csv
import requests
import os
import time

# ------------------ Utilities ------------------
def safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    try:
        # Handle "In Stock" or similar
        if isinstance(value, str) and "in stock" in value.lower():
            return 100  # default stock for "In Stock"
        return int(value)
    except (ValueError, TypeError):
        return default

def post_with_retries(url, data, retries=3, delay=1):
    for attempt in range(retries):
        try:
            response = requests.post(url, json=data)
            if response.status_code in (200, 201):
                return response
            else:
                print(f"Attempt {attempt+1}: Failed with status {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt+1}: Request error: {e}")
        time.sleep(delay)
    return None

# ------------------ Config ------------------
API_URL = os.getenv("API_URL", "https://bharat-product-web.onrender.com/api/products")

# ------------------ Import Function ------------------
def import_products(csv_path):
    if not os.path.exists(csv_path):
        print(f"❌ File not found: {csv_path}")
        return

    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        total = 0
        success = 0
        skipped = 0
        failed = 0

        for row in reader:
            total += 1
            name = (row.get("name") or "").strip()
            price = safe_float(row.get("price"), default=None)

            if not name or price is None or price <= 0:
                print(f"⚠️ Skipped (invalid data): {name or 'Unnamed Product'} - Price: {row.get('price')}")
                skipped += 1
                continue

            stock_val = row.get("stock")
            stock = safe_int(stock_val, default=50)  # default stock if empty or invalid

            mode = (row.get("mode") or "general").strip().lower()  # default mode if missing

            product_data = {
                "name": name,
                "description": row.get("description") or "No description provided",
                "brand": row.get("brand") or "Unknown",
                "category": row.get("category") or "Misc",
                "price": price,
                "region": row.get("region") or "India",
                "tags": row.get("tags") or "",
                "image_url": row.get("image_url") if row.get("image_url", "").startswith("http") else "https://via.placeholder.com/300",
                "rating": safe_float(row.get("rating"), default=0.0),
                "stock": stock,
                "mode": mode
            }

            response = post_with_retries(API_URL, product_data)

            if response:
                print(f"✅ Added: {name} (Mode: {mode})")
                success += 1
            else:
                print(f"❌ Failed to add: {name} - trying next")
                failed += 1

            time.sleep(0.05)  # small delay to avoid server overload

        # ------------------ Summary ------------------
        print("\n📊 Import Summary:")
        print(f"Total products processed: {total}")
        print(f"Successfully added: {success}")
        print(f"Skipped (invalid data): {skipped}")
        print(f"Failed requests: {failed}")

# ------------------ Main ------------------
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, "products.csv")
    print(f"📄 Looking for: {csv_path}")
    import_products(csv_path)
