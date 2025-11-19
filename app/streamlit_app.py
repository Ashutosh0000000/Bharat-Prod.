import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt

API_BASE = "https://bharat-products-e0et.onrender.com/api"

# --- API Utilities ---
def api_get(path, params=None):
    try:
        r = requests.get(f"{API_BASE}/{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"GET failed: {e}")
        return {"total": 0, "items": []}

def api_post(path, data):
    try:
        r = requests.post(f"{API_BASE}/{path}", json=data, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        st.error(f"POST failed: {e}")
        return False

def api_put(path, data):
    try:
        r = requests.put(f"{API_BASE}/{path}", json=data, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        st.error(f"PUT failed: {e}")
        return False

def api_delete(path):
    try:
        r = requests.delete(f"{API_BASE}/{path}", timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        st.error(f"DELETE failed: {e}")
        return False

def wake_backend():
    if "waking_up" not in st.session_state:
        try:
            st.session_state["waking_up"] = True
            requests.get(f"{API_BASE}/products", timeout=30)
        except:
            pass
        finally:
            st.session_state["waking_up"] = False

# --- Helper: Need-based Matching ---
def find_products_by_need(need_text, products):
    """Match user-provided need text to product names and descriptions."""
    if not need_text:
        return []

    keywords = need_text.lower().split()
    matches = []

    for product in products:
        content = f"{product.get('name', '')} {product.get('description', '')}".lower()
        score = sum(1 for word in keywords if word in content)
        if score > 0:
            matches.append((product, score))

    matches.sort(key=lambda x: x[1], reverse=True)
    return [m[0] for m in matches]

# --- UI Helpers ---
def product_card(p, grid=True):
    img = str(p.get("image_url") or "")
    if img.startswith("http"):
        st.image(img, width=150 if grid else 100)
    else:
        st.write("🖼️ No image available")

    st.markdown(f"### {p['name']}")
    st.markdown(f"₹{p['price']} | ⭐ {p['rating']}")
    st.markdown(f"Stock: {p.get('stock', 'N/A')} | Views: {p.get('views', 0)}")
    st.write(p.get("description", "No description."))

    col1, col2, col3 = st.columns(3)
    if col1.button("🛒 Add", key=f"add_{p['id']}"):
        st.session_state.cart.append(p)
        st.success(f"Added {p['name']}")
    if col2.button("✏️ Edit", key=f"edit_{p['id']}"):
        st.session_state["edit_product_id"] = p["id"]
        st.session_state["refresh"] = not st.session_state.get("refresh", False)
    if col3.button("❌ Delete", key=f"del_{p['id']}"):
        if api_delete(f"products/{p['id']}"):
            st.success("Deleted!")
            st.session_state["refresh"] = not st.session_state.get("refresh", False)

# --- Dashboard ---
def show_dashboard(products):
    st.title("📊 Product Dashboard")

    if not products:
        st.warning("No products available to show insights.")
        return

    df = pd.DataFrame(products)

    if df.empty:
        st.warning("No product data to analyze.")
        return

    st.subheader("🔹 Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Products", len(df))
    col2.metric("Avg Price", f"₹{df['price'].mean():.2f}")
    col3.metric("Avg Rating", f"{df['rating'].mean():.2f}")
    col4.metric("Total Stock", int(df['stock'].sum()))

    st.subheader("🔥 Top Rated Products")
    top_rated = df.sort_values("rating", ascending=False).head(5)
    for _, p in top_rated.iterrows():
        st.markdown(f"**{p['name']}** - ₹{p['price']} ⭐{p['rating']}")
        if str(p.get("image_url", "")).startswith("http"):
            st.image(p["image_url"], width=120)
        st.caption(p.get("description", ""))

    st.subheader("👀 Most Viewed Products")
    if 'views' in df.columns:
        most_viewed = df.sort_values("views", ascending=False).head(5)
        for _, p in most_viewed.iterrows():
            st.markdown(f"**{p['name']}** - 👁️ {p['views']} views | ₹{p['price']}")
            if str(p.get("image_url", "")).startswith("http"):
                st.image(p["image_url"], width=100)
            st.caption(p.get("description", ""))

    st.subheader("📌 Products by Category")
    if 'category' in df and df['category'].notna().any():
        cat_counts = df['category'].value_counts()
        fig1, ax1 = plt.subplots()
        ax1.pie(cat_counts, labels=cat_counts.index, autopct='%1.1f%%', startangle=140)
        ax1.axis('equal')
        st.pyplot(fig1)
    else:
        st.info("No category data to plot.")

    st.subheader("💰 Average Price per Category")
    if 'category' in df and 'price' in df:
        avg_price_by_cat = df.groupby("category")["price"].mean()
        st.bar_chart(avg_price_by_cat)
    else:
        st.info("No data to show average price.")

    st.subheader("⭐ Rating Distribution")
    if 'rating' in df:
        fig2, ax2 = plt.subplots()
        ax2.hist(df['rating'].dropna(), bins=10, color='skyblue', edgecolor='black')
        ax2.set_xlabel("Rating")
        ax2.set_ylabel("Products")
        st.pyplot(fig2)

# --- Add Product ---
def show_add_product():
    st.title("➕ Add Product")
    with st.form("add_form"):
        name = st.text_input("Name")
        price = st.number_input("Price", 0.0)
        rating = st.number_input("Rating", 0.0, 5.0, step=0.1)
        category = st.text_input("Category")
        stock = st.number_input("Stock", 0, step=1)
        desc = st.text_area("Description")
        img = st.text_input("Image URL")

        if st.form_submit_button("Add") and name:
            data = {
                "name": name, "price": price, "rating": rating,
                "category": category, "stock": stock,
                "description": desc, "image_url": img,
                "views": 0
            }
            if api_post("products", data):
                st.success("Product added!")
                st.experimental_rerun()

# --- Edit Product ---
def show_edit_product(product):
    st.title(f"✏️ Edit: {product['name']}")
    with st.form(f"edit_{product['id']}"):
        name = st.text_input("Name", product["name"])
        price = st.number_input("Price", 0.0, value=product["price"])
        rating = st.number_input("Rating", 0.0, 5.0, step=0.1, value=product["rating"])
        category = st.text_input("Category", product.get("category", ""))
        stock = st.number_input("Stock", 0, step=1, value=product.get("stock", 0))
        desc = st.text_area("Description", product.get("description", ""))
        img = st.text_input("Image URL", product.get("image_url", ""))
        views = st.number_input("Views", 0, step=1, value=product.get("views", 0))

        if st.form_submit_button("Update"):
            updated = {
                "name": name, "price": price, "rating": rating,
                "category": category, "stock": stock,
                "description": desc, "image_url": img,
                "views": views
            }
            if api_put(f"products/{product['id']}", updated):
                st.success("Updated!")
                st.experimental_rerun()

# --- Product List ---
# --- Product List ---
def show_product_list():
    st.title("🛍️ Bharat Products")

    # --- Sidebar Filters ---
    st.sidebar.header("🔍 Filters")
    search = st.sidebar.text_input("Search")
    category = st.sidebar.text_input("Category")
    min_price = st.sidebar.number_input("Min ₹", value=0.0)
    max_price = st.sidebar.number_input("Max ₹", value=100000.0)
    sort_by = st.sidebar.selectbox("Sort By", ["", "price", "rating", "name"])
    order = st.sidebar.radio("Order", ["asc", "desc"])
    view_mode = st.sidebar.radio("View", ["Grid", "List"])

    params = {}
    if search:
        params["search"] = search
    if category:
        params["category"] = category
    if min_price > 0:
        params["min_price"] = min_price
    if max_price < 100000:
        params["max_price"] = max_price
    if sort_by:
        params["sort_by"] = sort_by
    if order:
        params["order"] = order

    items = api_get("products", params).get("items", [])
    if not items:
        st.warning("No products found.")
        return

    # Grid View
    if view_mode == "Grid":
        for i in range(0, len(items), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(items):
                    with cols[j]:
                        product_card(items[i + j])
    else:
        # List View
        for p in items:
            product_card(p, grid=False)
            st.markdown("---")

    # Edit view
    if "edit_product_id" in st.session_state:
        product_id = st.session_state.pop("edit_product_id")
        p = next((x for x in items if x["id"] == product_id), None)
        if p:
            show_edit_product(p)

# --- Help Me Choose ---
def show_need_based_search():
    st.sidebar.subheader("Need Help Choosing?")

    user_problem = st.sidebar.text_area("Describe your problem or what you need help with")
    if st.sidebar.button("Find Products"):
        if user_problem.strip():
            params = {"search": user_problem}
            products = api_get("products", params).get("items", [])
            if products:
                st.write(f"Found {len(products)} product(s) that may help:")
                for p in products:
                    product_card(p, grid=False)
            else:
                st.warning("No matching products found. Try different keywords.")
        else:
            st.info("Please describe your problem first.")

def main():
    st.set_page_config("Bharat Product Catalog", layout="wide")
    wake_backend()

    st.sidebar.title("📍 Navigate")
    view = st.sidebar.radio("Select View", ["Dashboard", "Product List", "Add Product", "Need Help Choosing?"])

    if "cart" not in st.session_state:
        st.session_state.cart = []

    if view == "Dashboard":
        products = api_get("products", {"limit": 1000}).get("items", [])
        show_dashboard(products)
    elif view == "Product List":
        show_product_list()
    elif view == "Add Product":
        show_add_product()
    elif view == "Need Help Choosing?":
        show_need_based_search()

if __name__ == "__main__":
    main()
