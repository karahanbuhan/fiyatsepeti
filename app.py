
import sqlite3
import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path("sepet_hafizasi.db")

CATEGORIES = [
    "Gıda", "Temizlik", "Kişisel Bakım", "Elektronik", "Ev", "Ulaşım", "Diğer"
]

UNITS = ["adet", "kg", "gr", "lt", "ml", "paket", "kutu", "şişe", "poşet", "diğer"]

MARKET_WORDS = [
    "bim", "a101", "migros", "şok", "sok", "carrefour", "hakmar",
    "file", "metro", "gratis", "rossmann", "trendyol", "hepsiburada"
]


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_date TEXT NOT NULL,
            item_name TEXT NOT NULL,
            category TEXT DEFAULT 'Diğer',
            quantity REAL DEFAULT 1,
            unit TEXT DEFAULT 'adet',
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            store TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def normalize_item_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"\s+", " ", name)
    return name


def normalize_store_name(store: str) -> str:
    store = store.strip()
    if not store:
        return ""
    return store.upper().replace("SOK", "ŞOK")


def add_purchase(purchase_date, item_name, category, quantity, unit, unit_price, store="", note=""):
    item_name = normalize_item_name(item_name)
    quantity = float(quantity)
    unit_price = float(unit_price)
    total_price = quantity * unit_price

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO purchases
        (purchase_date, item_name, category, quantity, unit, unit_price, total_price, store, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(purchase_date),
            item_name,
            category,
            quantity,
            unit,
            unit_price,
            total_price,
            normalize_store_name(store),
            note.strip(),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()


def load_data():
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM purchases ORDER BY purchase_date DESC, id DESC",
        conn,
    )
    conn.close()
    return df


def delete_purchase(row_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM purchases WHERE id = ?", (int(row_id),))
    conn.commit()
    conn.close()


def parse_number(value: str) -> float:
    return float(value.replace(",", "."))


def detect_global_date(raw: str) -> str:
    raw_lower = raw.lower()
    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", raw)
    if date_match:
        return date_match.group(1)
    if "dün" in raw_lower:
        return str(date.today() - pd.Timedelta(days=1))
    return str(date.today())


def detect_global_store(raw: str) -> str:
    raw_lower = raw.lower()
    # "BIM'den", "A101 den", "Migros'tan" gibi ifadeleri yakalar.
    for market in MARKET_WORDS:
        if re.search(rf"\b{re.escape(market)}\b", raw_lower):
            return normalize_store_name(market)
    return ""


def clean_item_text(text: str, store: str = "") -> str:
    text = text.lower()
    text = re.sub(r"\b20\d{2}-\d{2}-\d{2}\b", " ", text)
    text = re.sub(r"\b(bugün|bugun|dün|dun|aldım|aldim|alındı|alindi|aldık|aldik|market|mağaza|magaza|toplam)\b", " ", text)

    # Market isimlerini temizle.
    for market in MARKET_WORDS:
        text = re.sub(rf"\b{re.escape(market)}\b", " ", text)

    # Türkçe ekleri ve bağlaçları kabaca temizle.
    text = re.sub(r"\b(den|dan|ten|tan|de|da|ile|ve)\b", " ", text)
    text = re.sub(r"['’](den|dan|ten|tan|de|da)", " ", text)
    text = re.sub(r"[,.;:/\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_semicolon_lines(raw: str):
    """
    Çoklu yarı yapılandırılmış format:
    süt; 2026-05-20; 1; lt; 42; market=A101; kategori=Gıda
    domates; 2026-05-20; 2; kg; 130; market=BIM; kategori=Gıda
    """
    results = []
    errors = []

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        lines = [raw.strip()]

    for idx, line in enumerate(lines, start=1):
        if ";" not in line:
            continue

        parts = [p.strip() for p in line.split(";") if p.strip()]
        try:
            item = parts[0]
            p_date = parts[1] if len(parts) > 1 and re.match(r"\d{4}-\d{2}-\d{2}", parts[1]) else str(date.today())
            quantity = parse_number(parts[2]) if len(parts) > 2 else 1.0
            unit = parts[3].lower() if len(parts) > 3 else "adet"
            total_price = parse_number(re.sub(r"[^\d,.]", "", parts[4])) if len(parts) > 4 else 0.0

            store = ""
            category = "Gıda"
            for p in parts[5:]:
                low = p.lower()
                if low.startswith(("market=", "mağaza=", "magaza=", "store=")):
                    store = p.split("=", 1)[1].strip()
                elif low.startswith(("kategori=", "category=")):
                    category = p.split("=", 1)[1].strip()

            if not item or total_price <= 0:
                errors.append(f"{idx}. satırda ürün adı veya fiyat eksik.")
                continue

            results.append({
                "purchase_date": p_date,
                "item_name": item,
                "category": category,
                "quantity": quantity,
                "unit": unit,
                "unit_price": total_price / quantity,
                "store": store,
                "note": line,
            })
        except Exception as exc:
            errors.append(f"{idx}. satır çözümlenemedi: {exc}")

    return results, errors


def split_natural_language_items(raw: str):
    """
    Doğal metinde her ürün genelde bir fiyat ile biter:
    "2 kg domates 60 TL, 1 lt süt 42 TL, 3 paket makarna 75 TL"
    Bu fonksiyon fiyat bitişlerine göre parçalar.
    """
    price_pattern = re.compile(r"(\d+(?:[,.]\d+)?)\s*(tl|₺|lira)", re.IGNORECASE)
    matches = list(price_pattern.finditer(raw))

    if not matches:
        return []

    chunks = []
    previous_end = 0
    for m in matches:
        chunk = raw[previous_end:m.end()]
        # Baştaki virgül / ve gibi ayırıcıları temizle.
        chunk = re.sub(r"^[\s,.;:/\-]*(ve\s+)?", "", chunk.strip(), flags=re.IGNORECASE)
        if chunk:
            chunks.append(chunk)
        previous_end = m.end()

    return chunks


def parse_single_natural_chunk(chunk: str, global_date: str, global_store: str):
    price_match = re.search(r"(\d+(?:[,.]\d+)?)\s*(tl|₺|lira)", chunk.lower())
    if not price_match:
        return None, "Fiyat bulunamadı."

    total_price = parse_number(price_match.group(1))

    qty_match = re.search(
        r"(\d+(?:[,.]\d+)?)\s*(kg|gr|lt|ml|adet|paket|kutu|şişe|sise|poşet|poset)",
        chunk.lower()
    )

    quantity = parse_number(qty_match.group(1)) if qty_match else 1.0
    unit = qty_match.group(2) if qty_match else "adet"
    unit = unit.replace("sise", "şişe").replace("poset", "poşet")

    store = detect_global_store(chunk) or global_store

    # Ürün adı: miktar-birim ile fiyat arasındaki metin.
    if qty_match:
        item_segment = chunk[qty_match.end():price_match.start()]
    else:
        item_segment = chunk[:price_match.start()]

    item = clean_item_text(item_segment, store=store)

    # Eğer ürün adı boş kaldıysa, fiyat öncesinden miktarı çıkarıp tekrar dene.
    if not item:
        before_price = chunk[:price_match.start()]
        before_price = re.sub(
            r"\d+(?:[,.]\d+)?\s*(kg|gr|lt|ml|adet|paket|kutu|şişe|sise|poşet|poset)",
            " ",
            before_price,
            flags=re.IGNORECASE
        )
        item = clean_item_text(before_price, store=store)

    if not item:
        return None, f"Ürün adı tahmin edilemedi: {chunk}"

    return {
        "purchase_date": global_date,
        "item_name": item,
        "category": "Gıda",
        "quantity": quantity,
        "unit": unit,
        "unit_price": total_price / quantity,
        "store": store,
        "note": chunk.strip(),
    }, None


def parse_agent_text_multi(raw: str):
    raw = raw.strip()
    if not raw:
        return [], ["Metin boş."]

    # Yarı yapılandırılmış çoklu satır formatı varsa önce onu dene.
    if ";" in raw:
        parsed, errors = parse_semicolon_lines(raw)
        if parsed:
            return parsed, errors

    global_date = detect_global_date(raw)
    global_store = detect_global_store(raw)
    chunks = split_natural_language_items(raw)

    if not chunks:
        return [], ["Fiyat bulunamadı. Örnek: '2 kg domates 60 TL, 1 lt süt 42 TL'"]

    results = []
    errors = []
    for chunk in chunks:
        item, error = parse_single_natural_chunk(chunk, global_date, global_store)
        if error:
            errors.append(error)
        else:
            results.append(item)

    return results, errors


def to_excel_bytes(df: pd.DataFrame):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="AlisverisKayitlari")
    return output.getvalue()


def prepare_analytics_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["purchase_date"] = pd.to_datetime(out["purchase_date"], errors="coerce")
    out = out.dropna(subset=["purchase_date"])
    out["month"] = out["purchase_date"].dt.to_period("M").astype(str)
    out["day"] = out["purchase_date"].dt.date
    out["total_price"] = pd.to_numeric(out["total_price"], errors="coerce").fillna(0)
    out["unit_price"] = pd.to_numeric(out["unit_price"], errors="coerce").fillna(0)
    return out


def calculate_comparison(df: pd.DataFrame, item_name: str):
    item_df = df[df["item_name"] == item_name].copy()
    if len(item_df) < 2:
        return None

    item_df["purchase_date"] = pd.to_datetime(item_df["purchase_date"])
    item_df = item_df.sort_values("purchase_date")

    first = item_df.iloc[0]
    last = item_df.iloc[-1]

    old_price = float(first["unit_price"])
    new_price = float(last["unit_price"])
    diff = new_price - old_price
    rate = (diff / old_price) * 100 if old_price else 0

    return {
        "first_date": first["purchase_date"].date(),
        "last_date": last["purchase_date"].date(),
        "old_price": old_price,
        "new_price": new_price,
        "diff": diff,
        "rate": rate,
        "count": len(item_df),
        "unit": last["unit"],
    }


def seed_demo_data():
    demo = [
        ("2025-05-20", "süt", "Gıda", 1, "lt", 25, "A101", "Demo eski kayıt"),
        ("2026-01-12", "süt", "Gıda", 1, "lt", 34, "A101", "Demo kayıt"),
        ("2026-05-20", "süt", "Gıda", 1, "lt", 42, "A101", "Demo yeni kayıt"),
        ("2025-05-20", "domates", "Gıda", 1, "kg", 30, "BIM", "Demo eski kayıt"),
        ("2026-03-02", "domates", "Gıda", 1, "kg", 52, "BIM", "Demo kayıt"),
        ("2026-05-20", "domates", "Gıda", 1, "kg", 65, "BIM", "Demo yeni kayıt"),
        ("2026-04-10", "makarna", "Gıda", 2, "paket", 18.5, "Migros", "Demo kayıt"),
        ("2026-05-18", "makarna", "Gıda", 3, "paket", 21, "Migros", "Demo kayıt"),
        ("2026-05-19", "deterjan", "Temizlik", 1, "adet", 145, "ŞOK", "Demo kayıt"),
    ]
    for row in demo:
        add_purchase(*row)


st.set_page_config(page_title="Sepet Hafızası", page_icon="🛒", layout="wide")
init_db()

st.title("🛒 Sepet Hafızası")
st.caption("Kişisel alışveriş kayıtlarını tutan, Excel gibi listeleyen ve fiyat değişimlerini analiz eden agent.")

with st.sidebar:
    st.header("Proje")
    st.write("**Sepet Hafızası: Kişisel Alışveriş ve Fiyat Değişimi Takip Agent'ı**")
    st.write("Teknoloji: Python + SQLite + Streamlit")
    st.write("Veritabanı: `sepet_hafizasi.db`")
    if st.button("Demo verisi ekle"):
        seed_demo_data()
        st.success("Demo verileri eklendi.")

tab_agent, tab_manual, tab_dashboard, tab_records, tab_compare = st.tabs(
    ["Agent ile Çoklu Kayıt", "Manuel Kayıt", "Dashboard / Grafikler", "Kayıtlar / Excel", "Fiyat Karşılaştırması"]
)

with tab_agent:
    st.subheader("Tek prompt ile birden fazla ürün kaydet")
    st.write("Agent, tek cümledeki birden fazla ürünü fiyatlara göre ayrıştırır.")

    st.markdown("**Doğal metin örneği:**")
    st.code("Bugün BIM'den 2 kg domates 130 TL, 1 lt süt 42 TL, 3 paket makarna 75 TL aldım")

    st.markdown("**Daha garantili çoklu format:**")
    st.code(
        "domates; 2026-05-20; 2; kg; 130; market=BIM; kategori=Gıda\n"
        "süt; 2026-05-20; 1; lt; 42; market=A101; kategori=Gıda\n"
        "makarna; 2026-05-20; 3; paket; 75; market=Migros; kategori=Gıda"
    )

    text = st.text_area("Alışveriş promptu", height=160)
    col_a, col_b = st.columns([1, 2])

    with col_a:
        preview_button = st.button("Ayrıştırmayı önizle")
    with col_b:
        save_button = st.button("Ayrıştır ve kaydet")

    if preview_button or save_button:
        parsed_items, errors = parse_agent_text_multi(text)

        if errors:
            for err in errors:
                st.warning(err)

        if not parsed_items:
            st.error("Kaydedilebilir ürün bulunamadı.")
        else:
            preview_df = pd.DataFrame(parsed_items)
            preview_df["total_price"] = preview_df["quantity"] * preview_df["unit_price"]
            st.success(f"{len(parsed_items)} ürün ayrıştırıldı.")
            st.dataframe(preview_df, use_container_width=True)

            if save_button:
                for item in parsed_items:
                    add_purchase(**item)
                st.success(f"{len(parsed_items)} ürün veritabanına kaydedildi.")

with tab_manual:
    st.subheader("Manuel alışveriş kaydı")
    with st.form("manual_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            p_date = st.date_input("Tarih", value=date.today())
            item_name = st.text_input("Ürün adı", placeholder="ör. süt")
            category = st.selectbox("Kategori", CATEGORIES)
        with c2:
            quantity = st.number_input("Miktar", min_value=0.01, value=1.0, step=0.5)
            unit = st.selectbox("Birim", UNITS)
            unit_price = st.number_input("Birim fiyat (TL)", min_value=0.0, value=0.0, step=1.0)
        with c3:
            store = st.text_input("Market / Mağaza", placeholder="ör. A101")
            note = st.text_area("Not", placeholder="İsteğe bağlı")
            total_preview = quantity * unit_price
            st.metric("Toplam", f"{total_preview:.2f} TL")

        submitted = st.form_submit_button("Kaydet")
        if submitted:
            if not item_name.strip():
                st.error("Ürün adı boş olamaz.")
            elif unit_price <= 0:
                st.error("Birim fiyat 0'dan büyük olmalıdır.")
            else:
                add_purchase(p_date, item_name, category, quantity, unit, unit_price, store, note)
                st.success("Kayıt eklendi.")

with tab_dashboard:
    st.subheader("Harcama Dashboard'u")
    df = prepare_analytics_df(load_data())

    if df.empty:
        st.info("Grafikler için önce kayıt eklemelisin. Sol menüden demo verisi ekleyebilirsin.")
    else:
        min_date = df["purchase_date"].min().date()
        max_date = df["purchase_date"].max().date()

        f1, f2, f3 = st.columns(3)
        with f1:
            start_date = st.date_input("Başlangıç tarihi", value=min_date, min_value=min_date, max_value=max_date)
        with f2:
            end_date = st.date_input("Bitiş tarihi", value=max_date, min_value=min_date, max_value=max_date)
        with f3:
            selected_category = st.selectbox("Kategori", ["Tümü"] + sorted(df["category"].dropna().unique().tolist()))

        filtered = df[(df["purchase_date"].dt.date >= start_date) & (df["purchase_date"].dt.date <= end_date)].copy()
        if selected_category != "Tümü":
            filtered = filtered[filtered["category"] == selected_category]

        if filtered.empty:
            st.warning("Bu filtrelere göre kayıt bulunamadı.")
        else:
            total_spent = filtered["total_price"].sum()
            record_count = len(filtered)
            unique_items = filtered["item_name"].nunique()
            avg_record = filtered["total_price"].mean()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Toplam harcama", f"{total_spent:.2f} TL")
            m2.metric("Kayıt sayısı", f"{record_count}")
            m3.metric("Farklı ürün", f"{unique_items}")
            m4.metric("Ortalama kayıt tutarı", f"{avg_record:.2f} TL")

            st.divider()

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### Aylık toplam harcama")
                monthly = filtered.groupby("month", as_index=False)["total_price"].sum()
                monthly = monthly.rename(columns={"month": "Ay", "total_price": "Toplam Harcama"})
                st.bar_chart(monthly, x="Ay", y="Toplam Harcama", use_container_width=True)

            with c2:
                st.markdown("#### Günlük harcama çizgisi")
                daily = filtered.groupby("day", as_index=False)["total_price"].sum()
                daily = daily.rename(columns={"day": "Gün", "total_price": "Toplam Harcama"})
                st.line_chart(daily, x="Gün", y="Toplam Harcama", use_container_width=True)

            c3, c4 = st.columns(2)
            with c3:
                st.markdown("#### Kategoriye göre harcama")
                by_category = filtered.groupby("category", as_index=False)["total_price"].sum()
                by_category = by_category.sort_values("total_price", ascending=False)
                by_category = by_category.rename(columns={"category": "Kategori", "total_price": "Toplam Harcama"})
                st.bar_chart(by_category, x="Kategori", y="Toplam Harcama", use_container_width=True)

            with c4:
                st.markdown("#### Markete göre harcama")
                tmp = filtered.copy()
                tmp["store"] = tmp["store"].replace("", "Bilinmiyor").fillna("Bilinmiyor")
                by_store = tmp.groupby("store", as_index=False)["total_price"].sum()
                by_store = by_store.sort_values("total_price", ascending=False)
                by_store = by_store.rename(columns={"store": "Market", "total_price": "Toplam Harcama"})
                st.bar_chart(by_store, x="Market", y="Toplam Harcama", use_container_width=True)

            st.markdown("#### En çok harcama yapılan ürünler")
            top_items = filtered.groupby("item_name", as_index=False)["total_price"].sum()
            top_items = top_items.sort_values("total_price", ascending=False).head(10)
            top_items = top_items.rename(columns={"item_name": "Ürün", "total_price": "Toplam Harcama"})
            st.bar_chart(top_items, x="Ürün", y="Toplam Harcama", use_container_width=True)

            st.markdown("#### Aylık özet tablo")
            monthly_table = filtered.groupby("month").agg(
                toplam_harcama=("total_price", "sum"),
                kayit_sayisi=("id", "count"),
                farkli_urun=("item_name", "nunique")
            ).reset_index().rename(columns={"month": "ay"})
            st.dataframe(monthly_table, use_container_width=True)

with tab_records:
    st.subheader("Kayıtlar")
    df = load_data()

    if df.empty:
        st.info("Henüz kayıt yok. Demo verisi ekleyebilir veya manuel kayıt girebilirsin.")
    else:
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            item_filter = st.text_input("Ürün adına göre filtrele")
        with filter_col2:
            category_filter = st.selectbox("Kategori filtresi", ["Tümü"] + sorted(df["category"].dropna().unique().tolist()), key="records_category")
        with filter_col3:
            store_filter = st.text_input("Market filtresi")

        view = df.copy()
        if item_filter:
            view = view[view["item_name"].str.contains(item_filter.lower(), case=False, na=False)]
        if category_filter != "Tümü":
            view = view[view["category"] == category_filter]
        if store_filter:
            view = view[view["store"].str.contains(store_filter, case=False, na=False)]

        st.dataframe(view, use_container_width=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                "CSV indir",
                data=view.to_csv(index=False).encode("utf-8-sig"),
                file_name="sepet_hafizasi_kayitlari.csv",
                mime="text/csv",
            )
        with c2:
            st.download_button(
                "Excel indir",
                data=to_excel_bytes(view),
                file_name="sepet_hafizasi_kayitlari.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with c3:
            delete_id = st.number_input("Silinecek kayıt ID", min_value=0, value=0, step=1)
            if st.button("ID ile sil"):
                if delete_id > 0:
                    delete_purchase(delete_id)
                    st.success(f"{delete_id} ID'li kayıt silindi.")
                else:
                    st.warning("Silmek için geçerli bir ID gir.")

with tab_compare:
    st.subheader("Ürün bazlı fiyat değişimi")
    df = prepare_analytics_df(load_data())

    if df.empty or df["item_name"].nunique() == 0:
        st.info("Karşılaştırma için en az iki kayıt gerekir.")
    else:
        items = sorted(df["item_name"].dropna().unique().tolist())
        selected_item = st.selectbox("Ürün seç", items)
        result = calculate_comparison(df, selected_item)

        if result is None:
            st.warning("Bu ürün için en az iki farklı kayıt olmalı.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("İlk birim fiyat", f"{result['old_price']:.2f} TL / {result['unit']}", str(result["first_date"]))
            m2.metric("Son birim fiyat", f"{result['new_price']:.2f} TL / {result['unit']}", str(result["last_date"]))
            m3.metric("Fiyat değişimi", f"%{result['rate']:.2f}", f"{result['diff']:.2f} TL")

            st.write(
                f"Yorum: **{selected_item}** için {result['count']} kayıt üzerinden "
                f"ilk ve son birim fiyat karşılaştırıldı. Formül: "
                f"`((son fiyat - ilk fiyat) / ilk fiyat) * 100`."
            )

            chart_df = df[df["item_name"] == selected_item].copy()
            chart_df = chart_df.sort_values("purchase_date")
            price_history = chart_df[["purchase_date", "unit_price"]].rename(
                columns={"purchase_date": "Tarih", "unit_price": "Birim Fiyat"}
            )
            st.line_chart(price_history, x="Tarih", y="Birim Fiyat", use_container_width=True)

            st.markdown("#### Bu ürünün geçmiş kayıtları")
            st.dataframe(chart_df.sort_values("purchase_date"), use_container_width=True)
